"""Relational data model (PostgreSQL in Docker, SQLite for local runs)."""
from __future__ import annotations

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Warehouse(Base):
    __tablename__ = "warehouse"
    id = Column(String(16), primary_key=True)
    plant = Column(String(8), nullable=False)
    name = Column(String(120), nullable=False)
    kind = Column(String(16), nullable=False)
    bounds = Column(JSON)


class WarehouseZone(Base):
    __tablename__ = "warehouse_zone"
    id = Column(String(24), primary_key=True)
    warehouse_id = Column(String(16), ForeignKey("warehouse.id"), nullable=False)
    code = Column(String(8), nullable=False)
    name = Column(String(120), nullable=False)
    kind = Column(String(16), nullable=False)
    rect = Column(JSON)


class WarehouseBay(Base):
    __tablename__ = "warehouse_bay"
    id = Column(String(32), primary_key=True)
    zone_id = Column(String(24), ForeignKey("warehouse_zone.id"), nullable=False)
    warehouse_id = Column(String(16), ForeignKey("warehouse.id"), nullable=False)
    code = Column(String(8), nullable=False)
    rect = Column(JSON)


class BundleStack(Base):
    __tablename__ = "bundle_stack"
    id = Column(String(40), primary_key=True)
    bay_id = Column(String(32), ForeignKey("warehouse_bay.id"), nullable=False)
    zone_id = Column(String(24), nullable=False)
    warehouse_id = Column(String(16), nullable=False)
    code = Column(String(8), nullable=False)
    kind = Column(String(16), nullable=False)
    x = Column(Float, nullable=False)
    z = Column(Float, nullable=False)
    yaw = Column(Float, default=0.0)
    max_levels = Column(Integer, nullable=False)
    length_m = Column(Float)
    width_m = Column(Float)
    current_height = Column(Integer, default=0)


class BundleStackLevel(Base):
    __tablename__ = "bundle_stack_level"
    id = Column(String(48), primary_key=True)
    stack_id = Column(String(40), ForeignKey("bundle_stack.id"), nullable=False, index=True)
    level = Column(Integer, nullable=False)
    location_code = Column(String(48), nullable=False, unique=True)
    bundle_id = Column(String(32), nullable=True, index=True)


class Bundle(Base):
    __tablename__ = "bundle"
    id = Column(String(32), primary_key=True)
    barcode = Column(String(32), unique=True, nullable=False)
    product_code = Column(String(16), nullable=False, index=True)
    product_name = Column(String(120))
    alloy = Column(String(16))
    finish = Column(String(48))
    length_mm = Column(Integer)
    pieces = Column(Integer)
    weight_kg = Column(Float)
    customer = Column(String(120), index=True)
    sales_order = Column(String(16), index=True)
    status = Column(String(16), index=True)
    produced_at = Column(DateTime)
    wrap = Column(String(16))


class RfidTag(Base):
    __tablename__ = "rfid_tag"
    epc = Column(String(32), primary_key=True)
    bundle_id = Column(String(32), ForeignKey("bundle.id"), nullable=False, index=True)
    tag_type = Column(String(32), default="UHF Gen2 SGTIN-96 (metal mount)")
    associated_at = Column(DateTime)


class BundleLocation(Base):
    __tablename__ = "bundle_location"
    bundle_id = Column(String(32), ForeignKey("bundle.id"), primary_key=True)
    location_kind = Column(String(16))
    warehouse_id = Column(String(16), index=True)
    zone_id = Column(String(24))
    bay_id = Column(String(32))
    stack_id = Column(String(40), index=True)
    level = Column(Integer)
    location_code = Column(String(64))
    x = Column(Float)
    y = Column(Float)
    z = Column(Float)
    updated_at = Column(DateTime)


class Forklift(Base):
    __tablename__ = "forklift"
    id = Column(String(8), primary_key=True)
    name = Column(String(40))
    role = Column(String(16))
    model = Column(String(64))
    rfid_reader = Column(String(64))
    uwb_tag = Column(String(32))


class ForkliftPosition(Base):
    __tablename__ = "forklift_position"
    forklift_id = Column(String(8), ForeignKey("forklift.id"), primary_key=True)
    x = Column(Float)
    z = Column(Float)
    heading = Column(Float)
    fork_height = Column(Float)
    state = Column(String(24))
    load_bundle_id = Column(String(32))
    updated_at = Column(DateTime)


class MovementTask(Base):
    __tablename__ = "movement_task"
    id = Column(String(16), primary_key=True)
    type = Column(String(16), index=True)
    status = Column(String(16), index=True)
    bundle_id = Column(String(32), index=True)
    sales_order = Column(String(16))
    forklift_id = Column(String(8), index=True)
    from_code = Column(String(64))
    to_code = Column(String(64))
    created_at = Column(DateTime)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    distance_m = Column(Float)
    path = Column(JSON)


class MovementEvent(Base):
    __tablename__ = "movement_event"
    id = Column(Integer, primary_key=True)
    ts = Column(DateTime, index=True)
    event_type = Column(String(16))
    bundle_id = Column(String(32), index=True)
    forklift_id = Column(String(8), index=True)
    task_id = Column(String(16))
    location_code = Column(String(64))
    x = Column(Float)
    z = Column(Float)


class SalesOrder(Base):
    __tablename__ = "sales_order"
    order_number = Column(String(16), primary_key=True)
    customer = Column(String(120))
    ship_to = Column(String(120))
    carrier = Column(String(64))
    status = Column(String(16), index=True)
    priority = Column(String(16))
    booked_at = Column(DateTime)
    released_at = Column(DateTime)
    staged_at = Column(DateTime)
    dispatched_at = Column(DateTime)
    lines = Column(JSON)


class SalesOrderBundle(Base):
    __tablename__ = "sales_order_bundle"
    id = Column(String(56), primary_key=True)
    order_number = Column(String(16), ForeignKey("sales_order.order_number"), index=True)
    bundle_id = Column(String(32), index=True)
    status = Column(String(16))


class DispatchManifest(Base):
    __tablename__ = "dispatch_manifest"
    id = Column(String(24), primary_key=True)
    order_number = Column(String(16), index=True)
    truck_id = Column(String(16))
    truck_plate = Column(String(24))
    expected_epcs = Column(JSON)
    status = Column(String(16))
    created_at = Column(DateTime)
    validated_at = Column(DateTime)
    result = Column(JSON)


class DispatchEvent(Base):
    __tablename__ = "dispatch_event"
    id = Column(Integer, primary_key=True)
    manifest_id = Column(String(24), index=True)
    ts = Column(DateTime)
    event_type = Column(String(16))
    epc = Column(String(32))
    bundle_id = Column(String(32))
    detail = Column(JSON)


class SimulationEvent(Base):
    __tablename__ = "simulation_event"
    id = Column(Integer, primary_key=True)
    ts = Column(DateTime, index=True)
    sim_t = Column(Float)
    type = Column(String(32), index=True)
    severity = Column(String(12))
    message = Column(Text)
    refs = Column(JSON)


ALL_TABLES = [m.__tablename__ for m in Base.__subclasses__()]
