import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./auth";
import { TaxonomyProvider } from "./taxonomy";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <TaxonomyProvider>
          <App />
        </TaxonomyProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
);
