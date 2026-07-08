import { RouterProvider } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "react-hot-toast";
import { router } from "@/router";
import { queryClient } from "@/lib/queryClient";

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: "#0f1620",
            color: "#e5e7eb",
            border: "1px solid rgba(148,163,184,0.14)",
            fontSize: 13,
            borderRadius: 12,
          },
          success: { iconTheme: { primary: "#22c55e", secondary: "#0f1620" } },
          error: { iconTheme: { primary: "#f87171", secondary: "#0f1620" } },
        }}
      />
    </QueryClientProvider>
  );
}
