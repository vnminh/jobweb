# PostgreSQL with the JobWeb demo database already loaded (CareerBuilder window 7).
# docker/assets/jobweb.dump is produced by docker/build_db_dump.sh. Build context: repository root.
FROM postgres:16.6-alpine AS seed
ENV PGDATA=/var/lib/postgresql/pgdata
COPY docker/assets/jobweb.dump /tmp/jobweb.dump
RUN set -eux; \
    mkdir -p "$PGDATA"; chown -R postgres:postgres "$PGDATA"; \
    echo jobweb > /tmp/pw; chown postgres /tmp/pw; \
    su-exec postgres initdb -D "$PGDATA" -U jobweb --pwfile=/tmp/pw --auth-local=trust --auth-host=scram-sha-256; \
    echo "host all all all scram-sha-256" >> "$PGDATA/pg_hba.conf"; \
    su-exec postgres pg_ctl -D "$PGDATA" -o "-c listen_addresses=''" -w start; \
    su-exec postgres createdb -U jobweb jobweb; \
    su-exec postgres pg_restore -U jobweb -d jobweb --no-owner --jobs 4 /tmp/jobweb.dump; \
    su-exec postgres psql -U jobweb -d jobweb -c "VACUUM ANALYZE"; \
    su-exec postgres pg_ctl -D "$PGDATA" -m fast -w stop; \
    rm /tmp/pw

FROM postgres:16.6-alpine
ENV PGDATA=/var/lib/postgresql/pgdata POSTGRES_USER=jobweb POSTGRES_PASSWORD=jobweb POSTGRES_DB=jobweb
COPY --from=seed --chown=postgres:postgres /var/lib/postgresql/pgdata /var/lib/postgresql/pgdata
