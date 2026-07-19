import { defineConfig, type UserConfigExport } from "@tarojs/cli";

export default defineConfig(async (merge) => {
  const base: UserConfigExport = {
    projectName: "mochi-scout",
    date: "2026-07-19",
    designWidth: 750,
    deviceRatio: { 750: 1 },
    sourceRoot: "src",
    outputRoot: "dist",
    framework: "react",
    compiler: "webpack5",
    cache: { enable: true },
    mini: {
      postcss: {
        pxtransform: { enable: true, config: {} },
        cssModules: { enable: false, config: { namingPattern: "module", generateScopedName: "[name]__[local]___[hash:base64:5]" } }
      }
    }
  };
  const envConfig = process.env.NODE_ENV === "development" ? (await import("./dev")).default : (await import("./prod")).default;
  return merge({}, base, envConfig);
});

