#!/usr/bin/env python3
"""Debug database to see what documents are stored."""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

engine = create_engine('sqlite:///legal_documents.db')
Session = sessionmaker(bind=engine)
session = Session()

try:
    # Direct SQL query
    result = session.execute(text('SELECT so_hieu, ten_van_ban FROM document_metadata LIMIT 15'))
    print("Documents in database:")
    print(f"{'so_hieu':<25} | {'ten_van_ban':<50}")
    print("-" * 80)
    for row in result:
        print(f"{row[0]:<25} | {row[1]}")
    
    # Search for "dân sự"
    print("\n\nSearching for 'dân sự':")
    result = session.execute(text("SELECT so_hieu, ten_van_ban FROM document_metadata WHERE ten_van_ban LIKE '%dân sự%' OR ten_van_ban LIKE '%dan su%'"))
    for row in result:
        print(f"{row[0]:<25} | {row[1]}")
        
    # Search for "luật"
    print("\n\nSearching for 'luật':")
    result = session.execute(text("SELECT so_hieu, ten_van_ban FROM document_metadata WHERE ten_van_ban LIKE '%luật%' OR ten_van_ban LIKE '%luat%' LIMIT 5"))
    for row in result:
        print(f"{row[0]:<25} | {row[1]}")
        
finally:
    session.close()
