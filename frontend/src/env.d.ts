/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL for the API. Defaults to `/api` (proxied by Vite in dev). */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
