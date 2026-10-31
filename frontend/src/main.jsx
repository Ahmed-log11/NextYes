import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";
import { LangProvider } from "./lib/i18n.jsx";
import { DemoProvider } from "./lib/store.jsx";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <LangProvider>
      <DemoProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </DemoProvider>
    </LangProvider>
  </React.StrictMode>
);
