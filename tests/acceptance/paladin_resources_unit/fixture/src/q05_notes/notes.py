def read_batch(connection, identifiers):
    return [
        connection.execute("SELECT body FROM notes WHERE id = ?", (key,)).fetchone()[0]
        for key in identifiers
    ]


def parse_label(text):
    return int(text)
