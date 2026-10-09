import http from "node:http";

const port = Number(process.argv[2]);
if (!Number.isInteger(port) || port < 1 || port > 65535) {
  throw new Error("Pass a valid local port for the proxy test backend.");
}

const server = http.createServer((request, response) => {
  if (request.url === "/health") {
    response.writeHead(200, { "content-type": "text/plain" });
    response.end("ok");
    return;
  }

  if (request.url === "/projects/proxy-redirect/submissions") {
    response.writeHead(307, {
      location: `http://127.0.0.1:${port}/projects/proxy-redirect/submissions/`,
    });
    response.end();
    return;
  }

  if (request.url === "/projects/proxy-redirect/write" && request.method === "POST") {
    response.writeHead(307, {
      location: `http://127.0.0.1:${port}/projects/proxy-redirect/write/`,
    });
    response.end();
    return;
  }

  if (request.url === "/projects/proxy-redirect/submissions/") {
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify([{ id: "canonical-route-reached" }]));
    return;
  }

  response.writeHead(404, { "content-type": "application/json" });
  response.end(JSON.stringify({ detail: "not found" }));
});

server.listen(port, "127.0.0.1");
