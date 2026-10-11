import { cp, mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const [port, backendURL] = process.argv.slice(2);
if (!port || !backendURL) {
  throw new Error("Usage: node e2e/start-standalone.mjs <port> <backend-url>");
}

const webRoot = process.cwd();
const standaloneRoot = resolve(webRoot, ".next/standalone");
const standaloneNext = resolve(standaloneRoot, ".next");

await mkdir(standaloneNext, { recursive: true });
await cp(resolve(webRoot, ".next/static"), resolve(standaloneNext, "static"), {
  recursive: true,
  force: true,
});
await cp(resolve(webRoot, "public"), resolve(standaloneRoot, "public"), {
  recursive: true,
  force: true,
});

process.chdir(standaloneRoot);
process.env.HOSTNAME = "127.0.0.1";
process.env.PORT = port;
process.env.BACKEND_INTERNAL_URL = backendURL;

await import(pathToFileURL(resolve(standaloneRoot, "server.js")).href);
