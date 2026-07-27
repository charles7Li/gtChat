import { readFile } from "node:fs/promises";

const errors = [];
const apiBase = (process.env.TARO_APP_API_BASE || "").trim();
const templateId = (process.env.TARO_APP_TASK_TEMPLATE_ID || "").trim();
const project = JSON.parse(await readFile(new URL("../project.config.json", import.meta.url), "utf8"));

if (!apiBase.startsWith("https://") || apiBase.includes("example.com")) {
  errors.push("TARO_APP_API_BASE must be the filed production HTTPS API domain");
}
if (!templateId) errors.push("TARO_APP_TASK_TEMPLATE_ID is required");
if (!/^wx[0-9a-fA-F]{16}$/.test(project.appid || "")) errors.push("project.config.json must contain the real WeChat AppID");
if (project.setting?.urlCheck !== true) errors.push("project.config.json setting.urlCheck must be true");

if (errors.length) {
  throw new Error(`release preflight failed:\n- ${errors.join("\n- ")}`);
}
console.log("mini-program release preflight passed");
