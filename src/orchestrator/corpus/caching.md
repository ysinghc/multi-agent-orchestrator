# Caching

Product catalogue responses are cached in Redis for 10 minutes. Cache keys include the locale, so translated pages never share an entry. Writes to a product invalidate its keys synchronously before the write request returns.
