import tempfile
import unittest
from pathlib import Path

from scoach.api import Application
from scoach.db import DEFAULT_CUSTOMERS, connect, initialize_schema


class YoungAdultPersonaTests(unittest.TestCase):
    def test_default_import_and_persona_catalog_include_young_adult_payday_story(self):
        self.assertIn("CUST01331", DEFAULT_CUSTOMERS)

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "demo.sqlite3"
            conn = connect(database)
            initialize_schema(conn)
            conn.execute("INSERT INTO customers VALUES('CUST01331','02270',18,'{}')")
            conn.commit()
            conn.close()

            status, response = Application(database).handle("GET", "/api/personas")
            self.assertEqual(status, 200, response)
            persona = next(
                item
                for item in response["data"]["personas"]
                if item["customer_id"] == "CUST01331"
            )
            self.assertEqual(persona["name"], "Kai")
            self.assertEqual(persona["story"], "Young-adult payday timing")


if __name__ == "__main__":
    unittest.main()
