from . import database, rag_context


def main():
    db = database.initialize_database()
    stats = rag_context.ingest_default_event_set(db=db)
    print(stats)


if __name__ == "__main__":
    main()
