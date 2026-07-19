export default {
  env: { NODE_ENV: '"production"' },
  defineConstants: {
    MOCHI_API_BASE: JSON.stringify(process.env.TARO_APP_API_BASE || "https://api.example.com"),
    MOCHI_TASK_TEMPLATE_ID: JSON.stringify(process.env.TARO_APP_TASK_TEMPLATE_ID || "")
  },
  mini: {}
};
