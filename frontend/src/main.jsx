import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App.jsx";
// Fonts are bundled (no Google request), so the app looks the same offline and over Tailscale.
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/chakra-petch/500.css";
import "@fontsource/chakra-petch/600.css";
import "@fontsource/chakra-petch/700.css";
import "./styles/theme.css";
import "./styles/app.css";
import { applyTheme, initialTheme } from "./lib/theme";

applyTheme(initialTheme()); // before first paint, so there is no light flash
window.addEventListener("vite:preloadError", () => window.location.reload());

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 15 * 1000 } } });

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
