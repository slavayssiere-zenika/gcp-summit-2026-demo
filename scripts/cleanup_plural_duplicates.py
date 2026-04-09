import psycopg2
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/competencies")

def get_singular(name: str) -> str:
    """Basic singularization logic for tech terms (English/French)."""
    low = name.lower()
    # Handle common plurals
    if low.endswith('es') and len(low) > 4: # e.g. 'Services' -> 'Servic' ? No, 'es' usually implies 'e' or 'es'
        # Special case for 'es' at the end
        if low.endswith('ies'): return name[:-3] + 'y'
        return name[:-1] # Usually 's' at the end of 'e'
    if (low.endswith('s') or low.endswith('x')) and len(low) > 2:
        return name[:-1]
    return name

def run_cleanup():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        
        logger.info("Fetching all competencies...")
        cur.execute("SELECT id, name FROM competencies")
        comps = cur.fetchall()
        
        # 1. First pass: Identify potential renames and merges
        canonical_map = {} # singular_lower -> { 'id': int, 'name': str }
        
        for cid, name in comps:
            singular_name = get_singular(name)
            sig_lower = singular_name.lower()
            
            if sig_lower not in canonical_map:
                # If this is the singular version, it's the candidate for canonical
                if singular_name == name:
                    canonical_map[sig_lower] = {'id': cid, 'name': name, 'merged': []}
                else:
                    # It's a plural, but we don't have a singular yet
                    # We'll check later if we find one, or we'll rename this one
                    canonical_map[sig_lower] = {'id': cid, 'name': name, 'merged': [], 'needs_rename': True}
            else:
                # Already have a candidate for this base name
                canonical_map[sig_lower]['merged'].append({'id': cid, 'name': name})
                
        # 2. Second pass: Action
        for sig, data in canonical_map.items():
            canonical_id = data['id']
            canonical_name = data['name']
            
            # If it's a plural-only entry, rename it to singular
            if data.get('needs_rename') and not data['merged']:
                new_name = get_singular(canonical_name)
                logger.info(f"Renaming plural-only competency: '{canonical_name}' -> '{new_name}'")
                cur.execute("UPDATE competencies SET name = %s WHERE id = %s", (new_name, canonical_id))
                canonical_name = new_name
            
            # Merge others
            for other in data['merged']:
                other_id = other['id']
                other_name = other['name']
                
                logger.info(f"Merging '{other_name}' (ID {other_id}) into '{canonical_name}' (ID {canonical_id})")
                
                # Move user associations
                cur.execute("""
                    INSERT INTO user_competency (user_id, competency_id, created_at)
                    SELECT user_id, %s, created_at FROM user_competency 
                    WHERE competency_id = %s
                    ON CONFLICT (user_id, competency_id) DO NOTHING
                """, (canonical_id, other_id))
                
                # Move children in tree
                cur.execute("UPDATE competencies SET parent_id = %s WHERE parent_id = %s", (canonical_id, other_id))
                
                # Cleanup
                cur.execute("DELETE FROM user_competency WHERE competency_id = %s", (other_id,))
                cur.execute("DELETE FROM competencies WHERE id = %s", (other_id,))
                
        conn.commit()
        logger.info("Database cleanup successful.")
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        if 'conn' in locals():
            conn.rollback()
    finally:
        if 'conn' in locals():
            cur.close()
            conn.close()

if __name__ == "__main__":
    run_cleanup()
