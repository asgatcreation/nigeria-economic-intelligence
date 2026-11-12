# Checks that R can reach the warehouse, so the R modelling scripts in r/
# read from the same database as the Python side rather than from a copy.
#
# Settings are read from .env when it exists and from the environment
# otherwise, which is how this runs unchanged both locally (Docker on
# 127.0.0.1:5434) and in CI (a service container on 127.0.0.1:5432).
# The defaults mirror config.py.

if (file.exists(".env")) {
  lines <- readLines(".env", warn = FALSE)
  lines <- lines[nzchar(trimws(lines)) & !grepl("^[[:space:]]*#", lines)]

  eq <- regexpr("=", lines, fixed = TRUE)
  valid <- eq > 1
  lines <- lines[valid]
  eq <- eq[valid]

  keys <- trimws(substr(lines, 1, eq - 1))
  values <- trimws(substring(lines, eq + 1))
  vars <- setNames(values, keys)

  # The environment wins, so CI does not need a .env file on disk.
  vars <- vars[!nzchar(Sys.getenv(names(vars)))]
  if (length(vars) > 0) {
    do.call(Sys.setenv, as.list(vars))
  }
}

required <- c("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")
missing <- required[!nzchar(Sys.getenv(required))]

if (length(missing) > 0) {
  stop(
    "Required database settings are missing from .env and the environment: ",
    paste(missing, collapse = ", ")
  )
}

host <- Sys.getenv("POSTGRES_HOST", "127.0.0.1")
port <- as.integer(Sys.getenv("POSTGRES_PORT", "5434"))

con <- DBI::dbConnect(
  RPostgres::Postgres(),
  dbname = Sys.getenv("POSTGRES_DB"),
  host = host,
  port = port,
  user = Sys.getenv("POSTGRES_USER"),
  password = Sys.getenv("POSTGRES_PASSWORD")
)

result <- DBI::dbGetQuery(
  con,
  "SELECT current_database() AS database,
          current_user AS connected_user,
          version() AS server_version"
)

print(result)
DBI::dbDisconnect(con)
cat("\nR PostgreSQL connection successful at ", host, ":", port, "\n", sep = "")
