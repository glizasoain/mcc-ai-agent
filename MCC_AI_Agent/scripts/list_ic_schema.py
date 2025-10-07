import json
import mysql.connector
from app.db import get_db_cfg


def list_schema(schema: str) -> dict:
	cfg = get_db_cfg()
	conn = mysql.connector.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"], password=cfg["password"])
	cur = conn.cursor()
	cur.execute(
		"""
		SELECT TABLE_NAME
		FROM INFORMATION_SCHEMA.TABLES
		WHERE TABLE_SCHEMA = %s
		ORDER BY TABLE_NAME
		""",
		(schema,),
	)
	tables = [r[0] for r in cur.fetchall()]
	result = {"schema": schema, "tables": []}
	for t in tables:
		cur.execute(
			"""
			SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_KEY
			FROM INFORMATION_SCHEMA.COLUMNS
			WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
			ORDER BY ORDINAL_POSITION
			""",
			(schema, t),
		)
		cols = cur.fetchall()
		result["tables"].append(
			{
				"name": t,
				"columns": [
					{"name": c[0], "type": c[1], "nullable": c[2], "key": c[3]} for c in cols
				],
			}
		)
	cur.close(); conn.close()
	return result


if __name__ == "__main__":
	print(json.dumps(list_schema("ic_optimization")))


