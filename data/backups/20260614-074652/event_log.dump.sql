PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;
CREATE TABLE process_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_uuid TEXT NOT NULL,
                phase_number INTEGER,
                step_name TEXT,
                event TEXT NOT NULL,
                detail TEXT,
                timestamp TEXT NOT NULL
            );
INSERT INTO process_events VALUES(1,'ee8c3010-e2b5-48a3-b160-0cd34a874ee6',NULL,NULL,'workflow_created',NULL,'2026-03-29T14:09:04.043778+00:00');
INSERT INTO process_events VALUES(2,'ee8c3010-e2b5-48a3-b160-0cd34a874ee6',NULL,NULL,'workflow_paused',NULL,'2026-03-29T14:09:08.219002+00:00');
INSERT INTO process_events VALUES(3,'ee8c3010-e2b5-48a3-b160-0cd34a874ee6',NULL,NULL,'workflow_resumed',NULL,'2026-03-29T14:09:10.264259+00:00');
INSERT INTO process_events VALUES(4,'ee8c3010-e2b5-48a3-b160-0cd34a874ee6',NULL,NULL,'workflow_paused',NULL,'2026-03-29T14:09:11.002644+00:00');
INSERT INTO sqlite_sequence VALUES('process_events',4);
CREATE INDEX idx_process_events_workflow
            ON process_events (workflow_uuid, timestamp)
            ;
COMMIT;
