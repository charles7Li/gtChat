export default {
  env: { NODE_ENV: '"development"' },
  defineConstants: {
    MOCHI_API_BASE: JSON.stringify(process.env.TARO_APP_API_BASE || "http://127.0.0.1:8000"),
    MOCHI_TASK_TEMPLATE_ID: JSON.stringify(process.env.TARO_APP_TASK_TEMPLATE_ID || "")
  },
  mini: {}
};
