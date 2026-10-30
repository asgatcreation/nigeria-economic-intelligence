lines <- readLines(".env", warn = FALSE)
lines <- lines[nzchar(trimws(lines)) & !grepl("^[[:space:]]*#", lines)]

eq <- regexpr("=", lines, fixed = TRUE)
valid <- eq > 1
lines <- lines[valid]
eq <- eq[valid]

keys <- trimws(substr(lines, 1, eq - 1))
values <- trimws(substring(lines, eq + 1))
vars <- setNames(values, keys)

required <- c("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")

if (!all(required %in% names(vars))) {
  stop("Required database settings are missing from .env")
}

do.call(Sys.setenv, as.list(vars[required]))

con <- DBI::dbConnect(
  RPostgres::Postgres(),
  dbname = Sys.getenv("POSTGRES_DB"),
  host = "127.0.0.1",
  port = 5434,
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
cat("\nR PostgreSQL connection successful.\n")
