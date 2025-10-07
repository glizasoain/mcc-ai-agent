import json
from app.db import get_connection


def count_rows(table: str):
	try:
		conn = get_connection()
		cur = conn.cursor()
		cur.execute("SELECT COUNT(*) FROM " + table)
		n = int((cur.fetchone() or [0])[0])
		cur.close(); conn.close()
		return n
	except Exception as e:
		return f"error: {e}"


def main():
	results = {
		"merchants": count_rows("merchants"),
		"mcc_codes": count_rows("mcc_codes"),
		"merchant_kpis_monthly": count_rows("merchant_kpis_monthly"),
		"mcc_portfolio": count_rows("mcc_portfolio"),
		"brand_registry": count_rows("brand_registry"),
	}
	print(json.dumps(results))


if __name__ == "__main__":
	main()


