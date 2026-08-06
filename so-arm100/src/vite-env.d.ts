/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ESTOP_COMMAND?: string;
  readonly VITE_TORQUE_ENABLE_COMMAND?: string;
  readonly VITE_TORQUE_DISABLE_COMMAND?: string;
  readonly VITE_FEETECH_CALIBRATION?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
