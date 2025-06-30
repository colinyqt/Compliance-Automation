import os
import sqlite3

class MeterDatabase:
    def __init__(self, db_path="testing.db"):
        self.db_path = db_path
        self._validate_database()

    def _validate_database(self):
        """Ensure database exists and has expected structure"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                if 'Meters' not in tables:
                    raise ValueError("Meters table not found in database")
                print(f"✅ Database validated: {len(tables)} tables found")
        except Exception as e:
            raise ValueError(f"Database validation failed: {e}")

    def find_meter_specs(self, model_number: str) -> dict:
        """Find meter specifications using the SQLite database"""
        if not os.path.exists(self.db_path):
            print(f"❌ Database file not found: {self.db_path}")
            return {}

        model_number = model_number.strip()
        print(f"🔍 Searching for meter: {model_number}")

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # Try multiple matching strategies based on your schema
                search_queries = [
                    ("EXACT model_name", "SELECT * FROM Meters WHERE model_name = ? LIMIT 1", (model_number,)),
                    ("EXACT device_short_name", "SELECT * FROM Meters WHERE device_short_name = ? LIMIT 1", (model_number,)),
                    ("EXACT series_name", "SELECT * FROM Meters WHERE series_name = ? LIMIT 1", (model_number,)),
                    ("CASE-INSENSITIVE model_name", "SELECT * FROM Meters WHERE UPPER(model_name) = UPPER(?) LIMIT 1", (model_number,)),
                    ("CASE-INSENSITIVE device_short_name", "SELECT * FROM Meters WHERE UPPER(device_short_name) = UPPER(?) LIMIT 1", (model_number,)),
                    ("PARTIAL model_name", "SELECT * FROM Meters WHERE model_name LIKE ? LIMIT 1", (f"%{model_number}%",)),
                    ("PARTIAL device_short_name", "SELECT * FROM Meters WHERE device_short_name LIKE ? LIMIT 1", (f"%{model_number}%",)),
                    ("PARTIAL product_name", "SELECT * FROM Meters WHERE product_name LIKE ? LIMIT 1", (f"%{model_number}%",)),
                ]

                meter_row = None
                matched_by = None

                for search_name, query, params in search_queries:
                    cursor.execute(query, params)
                    meter_row = cursor.fetchone()
                    if meter_row:
                        matched_by = search_name
                        break

                if not meter_row:
                    print(f"❌ No meter found matching: {model_number}")
                    return {}

                meter_id = meter_row["id"]
                specs = dict(meter_row)
                print(f"✅ Found meter: {specs.get('model_name', model_number)} (ID: {meter_id}) via {matched_by}")

                # Fetch all related specifications using your actual table structure
                cursor.execute("SELECT application FROM DeviceApplications WHERE meter_id = ?", (meter_id,))
                specs["applications"] = [row[0] for row in cursor.fetchall()]

                cursor.execute("SELECT analysis_feature FROM PowerQualityAnalysis WHERE meter_id = ?", (meter_id,))
                specs["power_quality_features"] = [row[0] for row in cursor.fetchall()]

                cursor.execute("SELECT measurement_type FROM Measurements WHERE meter_id = ?", (meter_id,))
                specs["measurements"] = [row[0] for row in cursor.fetchall()]

                cursor.execute("SELECT accuracy_class FROM AccuracyClasses WHERE meter_id = ?", (meter_id,))
                specs["accuracy_classes"] = [row[0] for row in cursor.fetchall()]

                cursor.execute("SELECT parameter, accuracy FROM MeasurementAccuracy WHERE meter_id = ?", (meter_id,))
                specs["measurement_accuracy"] = {row[0]: row[1] for row in cursor.fetchall()}

                cursor.execute("SELECT protocol, support FROM CommunicationProtocols WHERE meter_id = ?", (meter_id,))
                specs["communication_protocols"] = {row[0]: row[1] for row in cursor.fetchall()}

                cursor.execute("SELECT recording_type FROM DataRecordings WHERE meter_id = ?", (meter_id,))
                specs["data_recording"] = [row[0] for row in cursor.fetchall()]

                cursor.execute("SELECT certification FROM Certifications WHERE meter_id = ?", (meter_id,))
                specs["certifications"] = [row[0] for row in cursor.fetchall()]

                cursor.execute("SELECT io_type, description FROM InputsOutputs WHERE meter_id = ?", (meter_id,))
                specs["inputs_outputs"] = [
                    {"type": row[0], "description": row[1]}
                    for row in cursor.fetchall()
                ]

                spec_count = sum([
                    len(specs.get("applications", [])),
                    len(specs.get("power_quality_features", [])),
                    len(specs.get("measurements", [])),
                    len(specs.get("accuracy_classes", [])),
                    len(specs.get("measurement_accuracy", {})),
                    len(specs.get("communication_protocols", {})),
                    len(specs.get("data_recording", [])),
                    len(specs.get("certifications", [])),
                    len(specs.get("inputs_outputs", [])),
                ])

                print(f"📊 Loaded meter specs with {spec_count} detailed specifications")
                return specs

        except Exception as e:
            print(f"❌ Error querying database: {e}")
            import traceback
            traceback.print_exc()
            return {}