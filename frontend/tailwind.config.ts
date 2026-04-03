import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "media",
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        status: {
          applied: "#3b82f6",
          interview: "#22c55e",
          rejected: "#ef4444",
          flagged: "#f59e0b",
          withdrawn: "#6b7280",
        },
      },
      boxShadow: {
        panel: "0 24px 80px -36px rgba(15, 23, 42, 0.35)",
      },
      backgroundImage: {
        "mesh-light":
          "radial-gradient(circle at top left, rgba(14, 165, 233, 0.16), transparent 32%), radial-gradient(circle at top right, rgba(59, 130, 246, 0.12), transparent 28%), linear-gradient(180deg, rgba(248, 250, 252, 0.98), rgba(241, 245, 249, 0.96))",
        "mesh-dark":
          "radial-gradient(circle at top left, rgba(14, 165, 233, 0.18), transparent 30%), radial-gradient(circle at top right, rgba(16, 185, 129, 0.14), transparent 24%), linear-gradient(180deg, rgba(2, 6, 23, 0.98), rgba(15, 23, 42, 0.98))",
      },
    },
  },
  plugins: [],
};

export default config;
