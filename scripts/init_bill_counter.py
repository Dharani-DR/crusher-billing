import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from models import Base, Bill  # noqa: E402

def main():
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'instance', 'data.db')
    db_uri = f"sqlite:///{os.path.abspath(db_path).replace(os.sep, '/')}"
    engine = create_engine(db_uri, echo=False)
    Session = sessionmaker(bind=engine)
    session = Session()
    Base.metadata.create_all(engine)
    last_bill = session.query(Bill).order_by(Bill.id.desc()).first()
    print(f"Initialized. Last bill: {last_bill.bill_no if last_bill else 'None'}")

if __name__ == "__main__":
    main()


