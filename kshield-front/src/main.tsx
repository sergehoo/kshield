import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles/index.css";
import { applyTheme, useThemeStore } from "@/lib/theme";

// Applique le thème persisté (fallback aux préférences OS)
applyTheme(useThemeStore.getState().mode);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
