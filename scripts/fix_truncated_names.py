import psycopg2
import os

DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/competencies")

FIXES = {
    "Vue.j": "Vue.js",
    "Cloud & DevOp": "Cloud & DevOps",
    "Kubernete": "Kubernetes",
    "AW": "AWS",
    "Linu": "Linux",
    "Prometheu": "Prometheus",
    "FS": "FSx",
    "SN": "SNS",
    "Azure DN": "Azure DNS",
    "Serverles": "Serverless",
    "Node.j": "Node.js",
    "Expres": "Express",
    "EC": "ECS",
    "Ruby On Rail": "Ruby on Rails",
    "CS": "CSS",
    "Ngin": "Nginx",
    "DevOp": "DevOps",
    "Jenkin": "Jenkins",
    "AngularJ": "AngularJS"
}

def run_fix():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    
    for wrong, right in FIXES.items():
        cur.execute("UPDATE competencies SET name = %s WHERE name = %s", (right, wrong))
        print(f"Fixed: {wrong} -> {right}")
        
    conn.commit()
    cur.close()
    conn.close()

if __name__ == "__main__":
    run_fix()
