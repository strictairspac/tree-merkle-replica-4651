import { api } from "../api/workbench.js";
import { errorText, field } from "../components/common/fields.js";
import { empty, pageHeading, section } from "../components/common/panel.js";
import { table } from "../components/common/table.js";
import { submit } from "../hooks/submit.js";
import { navigate } from "../router/router.js";
import { el } from "../utils/dom.js";

function queueForm(config, selected) {
  const form = el("form", {class: "queue-form"},
    field(config.parameter_label, el("input", {
      name: "parameter", type: "number", min: 1, max: config.max_parameter, required: true, value: config.default_parameter,
    })),
    el("button", {type: "submit"}, "提交执行"), errorText());
  submit(form, async values => {
    const run = await api.enqueue(selected.id, {parameter: Number(values.get("parameter"))});
    navigate(`runs/${run.id}`);
  });
  return form;
}

function journalForm(selected) {
  const count = selected.payload?.journal?.length || 0;
  const form = el("form", {},
    field("补录变更流水", el("textarea", {
      name: "records", required: true, rows: 6, spellcheck: "false",
      placeholder: '[{"seq": 43, "tree": 1235, "at": "2026-11-26T08:55+08:00", "before": {"street": "东砖街", "status": "待修枝", "revision": 2}, "after": {"street": "东砖街", "status": "巡检完成", "revision": 3}}]',
    }), `已有 ${count} 条；只追加不改写，流水号不可与已有重复。`),
    errorText(), el("button", {type: "submit"}, "补录流水"));
  submit(form, async values => {
    let records;
    try {
      records = JSON.parse(values.get("records"));
    } catch {
      throw new Error("流水 JSON 无法解析，请检查括号、引号和逗号");
    }
    if (!Array.isArray(records) || records.length === 0) throw new Error("需要非空的 JSON 数组");
    const entry = await api.appendJournal(selected.id, {records});
    form.replaceWith(el("p", {class: "empty"},
      `已补录 ${records.length} 条，现有 ${entry.payload?.journal?.length || 0} 条变更流水；可回执行页补缺续跑。`));
  });
  return form;
}

function registration(config, selected) {
  const data = selected ? JSON.stringify(selected.payload, null, 2) : "{}";
  const form = el("form", {id: "case-form"},
    field("名称", el("input", {name: "title", required: true, minlength: 2, maxlength: 120, value: selected ? `${selected.title} · 复演` : ""})),
    field("说明", el("input", {name: "description", maxlength: 420, value: selected?.description || ""})),
    field(`${config.unit}内容`, el("textarea", {name: "payload", spellcheck: "false", required: true, rows: 12}, data),
      selected ? "可以保留演示数据，也可以编辑 JSON 后保存。" : "输入业务 JSON。"),
    errorText(), el("button", {type: "submit"}, "保存资料"));
  submit(form, async values => {
    let payload;
    try {
      payload = JSON.parse(values.get("payload"));
    } catch {
      throw new Error("资料 JSON 无法解析，请检查括号、引号和逗号");
    }
    const entry = await api.createCase({title: values.get("title"), description: values.get("description"), payload});
    navigate(`cases/${entry.id}`);
  });
  return form;
}

export async function casesPage(config, user, route) {
  const cases = await api.cases();
  const selected = cases.find(item => item.id === route.id) ?? cases.at(-1);
  const operator = user.role === "operator";
  return el("div", {class: "page"},
    pageHeading(config.modules[1], `${config.unit} · ${config.fixture}`),
    section("资料目录", cases.length ? table(["编号", "名称", "说明", "操作"], cases.map(item =>
      [item.code, item.title, item.description,
        el("a", {href: `#cases/${item.id}`, "aria-current": item.id === selected?.id ? "true" : null}, "选用")]), "资料目录") :
      empty("这里还没有资料。")),
    el("div", {class: "split case-split"},
      section(selected ? selected.title : "等待选择资料", selected ?
        [el("p", {}, selected.description), operator ? queueForm(config, selected) : empty("当前账号可查看此资料。"),
          operator ? el("details", {}, el("summary", {}, "补录变更流水"), journalForm(selected)) : null,
          el("details", {}, el("summary", {}, "查看业务数据"), el("pre", {}, JSON.stringify(selected.payload, null, 2)))] :
        empty("先登记一条资料，再提交执行。")),
      operator ? section("登记新资料", registration(config, selected)) : null));
}
