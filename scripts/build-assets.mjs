import * as esbuild from "esbuild";

const files = [
  "static/reverie-home.css",
  "static/reverie-list-page.css",
  "static/reverie-shared.js",
  "static/reverie-home.js",
  "static/reverie-list-page.js",
  "static/reverie-search.js",
  "static/reverie-entities.js",
  "static/reverie-uploads.js",
  "static/reverie-capture.js",
  "static/service-worker.js",
];

for (const file of files) {
  const ext = file.endsWith(".css") ? "css" : "js";
  const outfile = file.replace(new RegExp(`\\.${ext}$`), `.min.${ext}`);
  await esbuild.build({
    entryPoints: [file],
    outfile,
    bundle: false,
    minify: true,
    sourcemap: false,
    legalComments: "none",
    logLevel: "warning",
  });
}
