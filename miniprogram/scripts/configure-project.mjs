import { readFile, writeFile } from "node:fs/promises";

const appid = (process.env.WECHAT_APP_ID || "").trim();
if (!/^wx[0-9a-fA-F]{16}$/.test(appid)) {
  throw new Error("WECHAT_APP_ID must be a valid mini-program AppID (wx + 16 hexadecimal characters)");
}
const url = new URL("../project.config.json", import.meta.url);
const project = JSON.parse(await readFile(url, "utf8"));
project.appid = appid;
project.setting = { ...(project.setting || {}), urlCheck: true };
await writeFile(url, `${JSON.stringify(project, null, 2)}\n`, "utf8");
console.log("project.config.json updated for the real WeChat AppID");
