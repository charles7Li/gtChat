/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_MOCHI_ADMIN_TOKEN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
