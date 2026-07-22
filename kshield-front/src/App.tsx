import { RouterProvider } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "react-hot-toast";
import { router } from "@/router";
import { queryClient } from "@/lib/queryClient";
import { ErrorBoundary } from "@/components/ErrorBoundary";

export default function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <RouterProvider
          router={router}
          future={{ v7_startTransition: true }}
        />
        <Toaster
          position="top-right"
          toastOptions={{
            style: {
              background: "rgb(var(--c-surface-card))",
              color: "rgb(var(--c-ink))",
              border: "1px solid rgb(var(--c-surface-border))",
              fontSize: 13,
              borderRadius: 12,
              boxShadow: "0 10px 30px rgb(0 0 0 / var(--shadow-strength))",
            },
            success: { iconTheme: { primary: "rgb(var(--c-ok))", secondary: "rgb(var(--c-surface-card))" } },
            error: { iconTheme: { primary: "rgb(var(--c-danger))", secondary: "rgb(var(--c-surface-card))" } },
          }}
        />
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
