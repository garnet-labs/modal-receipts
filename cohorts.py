"""Cohort definitions: what runs inside the sandboxes. Edit freely."""

# Real packages agents install all day. Picked from the npm/PyPI top lists plus the
# well-known native/binary ones; nothing here is constructed.
NPM = [
    "lodash", "react", "express", "axios", "typescript", "next", "vite", "webpack", "eslint", "prettier",
    "jest", "vitest", "zod", "chalk", "commander", "dotenv", "uuid", "moment", "dayjs", "rxjs",
    "esbuild", "@swc/core", "sharp", "puppeteer", "playwright", "cypress", "sqlite3", "better-sqlite3",
    "bcrypt", "canvas", "prisma", "@prisma/client", "node-gyp", "fsevents", "core-js", "husky",
    "@sentry/cli", "electron", "node-sass", "sass", "tailwindcss", "@biomejs/biome", "turbo", "nx",
    "pnpm", "yarn", "serverless", "aws-sdk", "@aws-sdk/client-s3", "firebase", "mongodb", "pg",
    "mysql2", "redis", "ioredis", "socket.io", "ws", "graphql", "apollo-server", "@nestjs/core",
]
PIP = [
    "requests", "numpy", "pandas", "flask", "fastapi", "django", "pydantic", "sqlalchemy", "pytest", "black",
    "ruff", "mypy", "httpx", "aiohttp", "boto3", "botocore", "pillow", "matplotlib", "scipy", "scikit-learn",
    "playwright", "selenium", "opencv-python", "pyarrow", "polars", "duckdb", "psycopg2-binary", "cryptography",
    "grpcio", "protobuf", "torch", "transformers", "openai", "anthropic", "langchain", "llama-index",
    "jupyter", "ipython", "rich", "typer",
]


def install_specs():
    specs = []
    for p in NPM:
        specs.append({"label": f"npm:{p}", "cmd": f"bash /opt/garnet/workload-install.sh npm '{p}'"})
    for p in PIP:
        specs.append({"label": f"pip:{p}", "cmd": f"bash /opt/garnet/workload-install.sh pip '{p}'"})
    return specs


def bench_specs(n_each, profiles=("files", "procs", "net", "repo"), rulesets=("full",)):
    specs = []
    for prof in profiles:
        for rules in rulesets:
            for _ in range(n_each):
                specs.append({"label": f"bench:{prof}" + (f":{rules}" if rules != "full" else ""), "rules": rules,
                              "cmd": f"bash /opt/garnet/workload-bench.sh {prof}"})
    return specs


def task_specs(n, repo, constructed):
    return [{"label": "task:" + repo.rsplit("/", 1)[-1], "constructed": i < constructed,
             "cmd": f"bash /opt/garnet/workload.sh {repo} {'constructed' if i < constructed else ''}"} for i in range(n)]


def swebench_specs(rows_path, limit, only=""):
    """Rows from princeton-nlp/SWE-bench_Lite (datasets-server JSON). Gold patch = the
    accepted fix; FAIL_TO_PASS = the tests a grader checks. One image per instance."""
    import base64, json
    rows = json.load(open(rows_path))["rows"]
    if only != "":
        rows = [x for x in rows if only in x["row"]["instance_id"]]
    specs = []
    for item in rows[:limit]:
        r = item["row"]
        inst = r["instance_id"]
        image = "swebench/sweb.eval.x86_64." + inst.replace("__", "_1776_")
        tests = json.loads(r["FAIL_TO_PASS"]) if isinstance(r["FAIL_TO_PASS"], str) else r["FAIL_TO_PASS"]
        files = {
            "/work/patch.diff": base64.b64encode(r["patch"].encode()).decode(),
            "/work/test.diff": base64.b64encode(r["test_patch"].encode()).decode(),
            "/work/tests": base64.b64encode(("\n".join(tests) + "\n").encode()).decode(),
        }
        specs.append({"label": f"swebench:{inst}", "registry_image": image, "files": files,
                      "cmd": "bash /opt/garnet/workload-swebench.sh"})
    return specs
