import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

import openapiTS, { astToString } from "openapi-typescript";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const frontendDirectory = path.resolve(scriptDirectory, "..");
const repositoryDirectory = path.resolve(frontendDirectory, "..");
const outputPath = path.join(
  frontendDirectory,
  "src",
  "api",
  "generated",
  "schema.d.ts",
);
const checkOnly = process.argv.includes("--check");

function pythonCandidates() {
  const configured = process.env.AIDAM_PYTHON;
  return [
    configured,
    path.join(repositoryDirectory, ".venv", "Scripts", "python.exe"),
    path.join(repositoryDirectory, ".venv", "bin", "python"),
    "python3",
    "python",
  ].filter((candidate, index, candidates) => {
    return Boolean(candidate) && candidates.indexOf(candidate) === index;
  });
}

function exportSchema() {
  const failures = [];

  for (const candidate of pythonCandidates()) {
    if (path.isAbsolute(candidate) && !existsSync(candidate)) {
      continue;
    }

    const result = spawnSync(candidate, ["-m", "backend.api.export_openapi"], {
      cwd: repositoryDirectory,
      encoding: "utf8",
      windowsHide: true,
    });

    if (result.status === 0) {
      return JSON.parse(result.stdout);
    }

    failures.push(
      `${candidate}: ${result.error?.message ?? result.stderr.trim() ?? "failed"}`,
    );
  }

  throw new Error(
    `Unable to export OpenAPI. Set AIDAM_PYTHON to a Python 3.11+ project environment.\n${failures.join("\n")}`,
  );
}

const schema = exportSchema();
const generated = astToString(await openapiTS(schema, { alphabetize: true }));

if (checkOnly) {
  if (
    !existsSync(outputPath) ||
    readFileSync(outputPath, "utf8") !== generated
  ) {
    console.error(
      "Generated API types are stale. Run `pnpm api:generate` and commit the result.",
    );
    process.exitCode = 1;
  } else {
    console.log("Generated API types are current.");
  }
} else {
  mkdirSync(path.dirname(outputPath), { recursive: true });
  writeFileSync(outputPath, generated);
  console.log(`Generated ${path.relative(frontendDirectory, outputPath)}.`);
}
