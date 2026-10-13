"""03_crud_orm.py — CRUD with SQLAlchemy ORM: Java JPA/Hibernate → Python SQLAlchemy.

Migration from JPA Entity/EntityManager to SQLAlchemy ORM.
Each function shows the Java JPA equivalent in its docstring.

Java JPA pattern (what you're replacing):
─────────────────────────────────────────
    @Entity
    @Table(name = "cookbook_jdbc_products")
    public class Product {
        @Id @GeneratedValue
        private int id;
        @Column(nullable = false)
        private String val;
        private int cnt;
        private double price;
        // getters, setters, constructors...  (30+ lines)
    }

Python SQLAlchemy (what you'll write):
──────────────────────────────────────
    class Product(Base):
        __tablename__ = "cookbook_jdbc_products"
        id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
        val: Mapped[str] = mapped_column(String(200))
        cnt: Mapped[int] = mapped_column(default=0)
        price: Mapped[float] = mapped_column(default=0.0)

No getters/setters. No constructors. No @Column verbosity. 80% less code.
"""

from __future__ import annotations

from sqlalchemy import String, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

DATABASE_URL = "cubrid+pycubrid://dba@localhost:33000/testdb"


class Base(DeclarativeBase):
    pass


class Product(Base):
    """SQLAlchemy model — replaces JPA @Entity.

    Java JPA equivalent:
        @Entity
        @Table(name = "cookbook_jdbc_products")
        public class Product {
            @Id
            @GeneratedValue(strategy = GenerationType.IDENTITY)
            private int id;

            @Column(name = "val", nullable = false, length = 200)
            private String val;

            @Column(name = "cnt")
            private int cnt = 0;

            @Column(name = "price")
            private double price = 0.0;

            // Constructor, getters, setters (20+ lines omitted)
        }
    """

    __tablename__ = "cookbook_jdbc_products"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    val: Mapped[str] = mapped_column(String(200))
    cnt: Mapped[int] = mapped_column(default=0)
    price: Mapped[float] = mapped_column(default=0.0)

    def __repr__(self) -> str:
        return f"Product(id={self.id}, val={self.val!r}, cnt={self.cnt}, price={self.price:.2f})"


def create_tables(engine) -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    print("Created table 'cookbook_jdbc_products'")


def insert_products(engine) -> None:
    """Create (INSERT) using ORM.

    Java JPA:
        EntityManager em = emf.createEntityManager();
        em.getTransaction().begin();
        Product p = new Product();
        p.setVal("Widget A");
        p.setCnt(10);
        p.setPrice(29.99);
        em.persist(p);
        em.getTransaction().commit();
        em.close();

    Python — Session replaces EntityManager, no setters needed:
    """
    with Session(engine) as session:
        products = [
            Product(val="Widget A", cnt=10, price=29.99),
            Product(val="Widget B", cnt=5, price=19.99),
            Product(val="Gadget C", cnt=20, price=49.99),
            Product(val="Part D", cnt=100, price=2.50),
            Product(val="Tool E", cnt=8, price=34.99),
        ]
        session.add_all(products)
        session.commit()
        print(f"Inserted {len(products)} products")
        for p in products:
            print(f"  {p}")


def query_all(engine) -> None:
    """Read (SELECT) all rows.

    Java JPA:
        TypedQuery<Product> q = em.createQuery(
            "SELECT p FROM Product p ORDER BY p.id", Product.class
        );
        List<Product> products = q.getResultList();
        for (Product p : products) {
            System.out.println(p.getVal() + " $" + p.getPrice());
        }

    Python — select() + scalars(), direct attribute access:
    """
    with Session(engine) as session:
        stmt = select(Product).order_by(Product.id)
        products = session.scalars(stmt).all()

        print(f"\nAll products ({len(products)}):")
        for p in products:
            print(f"  {p.val:12s}  cnt={p.cnt:3d}  ${p.price:.2f}")


def query_filtered(engine) -> None:
    """Read with filtering.

    Java JPA (JPQL):
        TypedQuery<Product> q = em.createQuery(
            "SELECT p FROM Product p WHERE p.price > :minPrice ORDER BY p.price DESC",
            Product.class
        );
        q.setParameter("minPrice", 20.0);
        List<Product> result = q.getResultList();

    Python — method chaining replaces JPQL string building:
    """
    with Session(engine) as session:
        stmt = select(Product).where(Product.price > 20.0).order_by(Product.price.desc())
        products = session.scalars(stmt).all()

        print(f"\nProducts over $20 ({len(products)}):")
        for p in products:
            print(f"  {p.val:12s}  ${p.price:.2f}")


def query_aggregation(engine) -> None:
    """Aggregation queries.

    Java JPA:
        Query q = em.createQuery(
            "SELECT COUNT(p), AVG(p.price), SUM(p.cnt) FROM Product p"
        );
        Object[] result = (Object[]) q.getSingleResult();

    Python — func.count/avg/sum with type-safe result:
    """
    with Session(engine) as session:
        stmt = select(
            func.count(Product.id).label("total"),
            func.avg(Product.price).label("avg_price"),
            func.sum(Product.cnt).label("total_cnt"),
        )
        row = session.execute(stmt).one()
        print(
            f"\nAggregation: {row.total} products, avg ${row.avg_price:.2f}, total count {row.total_cnt}"
        )


def update_products(engine) -> None:
    """Update using ORM.

    Java JPA:
        em.getTransaction().begin();
        Product p = em.find(Product.class, id);
        p.setPrice(24.99);
        em.getTransaction().commit();

    Python — direct attribute assignment, Session auto-tracks changes:
    """
    with Session(engine) as session:
        product = session.scalar(select(Product).where(Product.val == "Widget A"))
        if product:
            old_price = product.price
            product.price = 24.99
            session.commit()
            print(f"\nUpdated Widget A: ${old_price:.2f} -> ${product.price:.2f}")

        stmt = select(Product).where(Product.price < 10.0)
        cheap = session.scalars(stmt).all()
        for p in cheap:
            p.cnt += 50
        session.commit()
        print(f"Restocked {len(cheap)} cheap products (+50 each)")


def delete_products(engine) -> None:
    """Delete using ORM.

    Java JPA:
        em.getTransaction().begin();
        Product p = em.find(Product.class, id);
        em.remove(p);
        em.getTransaction().commit();

    Python — session.delete(), auto-commits on context exit:
    """
    with Session(engine) as session:
        product = session.scalar(select(Product).where(Product.val == "Tool E"))
        if product:
            session.delete(product)
            session.commit()
            print(f"\nDeleted {product.val!r}")

        remaining = session.scalar(select(func.count(Product.id)))
        print(f"Remaining products: {remaining}")


def cleanup(engine) -> None:
    Base.metadata.drop_all(engine)
    print("\nCleaned up")


if __name__ == "__main__":
    engine = create_engine(DATABASE_URL)

    try:
        create_tables(engine)
        insert_products(engine)
        query_all(engine)
        query_filtered(engine)
        query_aggregation(engine)
        update_products(engine)
        query_all(engine)
        delete_products(engine)
    finally:
        cleanup(engine)
        engine.dispose()
