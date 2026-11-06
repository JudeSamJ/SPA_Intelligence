// Runs the API (uvicorn --reload) and the Vite dev server together; Ctrl+C stops both. No extra dependencies.
import { spawn } from "node:child_process";
const run = (cmd, args, name) => {
  const p = spawn(cmd, args, { stdio: ["ignore", "pipe", "pipe"], shell: process.platform === "win32" });
  const tag = (d) => String(d).split("\n").filter(Boolean).forEach((l) => console.log(`[${name}] ${l}`));
  p.stdout.on("data", tag);
  p.stderr.on("data", tag);
  p.on("exit", (c) => { console.log(`[${name}] exited (${c})`); process.exit(c ?? 0); });
  return p;
};
const procs = [
  run(process.env.PYTHON ?? "python", ["-m", "uvicorn", "backend.api.main:app", "--reload", "--port", "8000"], "api"),
  run("npm", ["--prefix", "frontend", "run", "dev"], "web"),
];
for (const s of ["SIGINT", "SIGTERM"]) process.on(s, () => { procs.forEach((p) => p.kill()); process.exit(0); });
console.log("API on http://localhost:8000   Frontend on http://localhost:5173");
