"""
.. module:: orm
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Contains the ORM associated with the akit database storage

.. moduleauthor:: Myron Walker <myron.walker@gmail.com>
"""

__author__ = "Myron Walker"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum
import json
import uuid


from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    Index,
    Integer,
    LargeBinary,
    String,
    Table,
    Text,
    VARCHAR,
    ForeignKey,
    TEXT,
    UniqueConstraint,
)
from sqlalchemy import inspect, func, text
from sqlalchemy.types import JSON

from sqlalchemy.orm import declarative_base, relationship, backref

from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.utc_datetime import UtcDateTime

class SerializableModel:
    """
        Mixin style class that adds serialization to data model objects.
    """

    def to_dict(self):
        """
            Iterates the formal data attributes of a model and outputs a dictionary
            with the data based on the model.
        """
        dval = {}

        model = type(self)
        mapper = inspect(model)
        for col in mapper.attrs:
            col_key = col.key
            dval[col_key] = str(getattr(self, col_key))

        return dval


    def to_json(self, indent=4):
        """
            Iterates the formal data attributes of a model and creates a dictionary
            with the data based on the model, then converts the dictionary to a
            JSON string.
        """
        model_dict = self.to_dict()
        json_str = json.dumps(model_dict, indent=indent)
        return json_str


PychestrateModelBase = declarative_base()


class AccountStatus(str, enum.Enum):
    """
        Enum-like class to represent the status of a user or enterprise account.
    """
    ACTIVE = 'active'
    INACTIVE = 'inactive'
    SUSPENDED = 'suspended'
    DELETED = 'deleted'

    @classmethod
    def is_valid(cls, status):
        return status in (cls.ACTIVE, cls.INACTIVE, cls.SUSPENDED, cls.DELETED)


class AuthenticationType(str, enum.Enum):
    """
        Enum-like class to represent the type of authentications that should be used to authenticate the user.
    """
    INTERNAL = 'internal'
    OAUTH = 'oauth2'


class RepositoryType(enum.Enum):
    """Enumeration describing the primary content maintained by a repository."""

    CODE = "code"
    DOCUMENTATION = "documentation"


class RepositoryScope(enum.Enum):
    """Enumeration describing the scope of artifacts provided by a repository."""

    PRODUCT = "product"
    LOCAL = "local"


class WorkQueueJobType(enum.Enum):
    """
        An enumeration that indicates the JobType of a WorkQueue item.  This indicates if a
        work item is a global work item available for execution on any qualified work site or
        if it is a local work item which is meant to execute locally.
    """
    Local = 1
    Global = 2


class WorkQueueState(enum.Enum):
    """
        An enumeration that indicates the JobType of a WorkQueue item.  This indicates if a
        work item is a global work item available for execution on any qualified work site or
        if it is a local work item which is meant to execute locally.
    """
    Enabled = 1
    Disabled = 2


class WorkPacketStatus(enum.Enum):
    """Enumeration of lifecycle states for a :class:`WorkPacket`."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    BLOCKED = "BLOCKED"


class BuildJobTemplate(PychestrateModelBase, SerializableModel):
    """
        A data model that stores global build job templates.
    """

    __tablename__ = "buildjob_template"

    id = Column('bjtmp_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    name = Column('bjtmp_name', VARCHAR(128), nullable=False, unique=True)
    description = Column('bjtmp_description', Text, nullable=True)
    specification = Column('bjtmp_specification', JSON, nullable=False)


class BuildTemplate(PychestrateModelBase, SerializableModel):
    """
        A data model that stores global build templates.
    """

    __tablename__ = "build_template"

    id = Column('btmp_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    name = Column('btmp_name', VARCHAR(128), nullable=False, unique=True)
    description = Column('btmp_description', Text, nullable=True)
    specification = Column('btmp_specification', JSON, nullable=False)


class TestJobTemplate(PychestrateModelBase, SerializableModel):
    """
        A data model that stores global test job templates.
    """

    __tablename__ = "testjob_template"

    id = Column('tjtmp_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    name = Column('tjtmp_name', VARCHAR(128), nullable=False, unique=True)
    description = Column('tjtmp_description', Text, nullable=True)
    specification = Column('tjtmp_specification', JSON, nullable=False)



class Product(PychestrateModelBase, SerializableModel):
    """A data model that represents a product composed from multiple components."""

    __tablename__ = "product"

    id = Column("prod_id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    name = Column("prod_name", VARCHAR(128), nullable=False, unique=True)
    description = Column("prod_description", Text, nullable=True)

    components = relationship(
        "ProductComponent",
        back_populates="product",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    product_repositories = relationship(
        "ProductToRepository",
        back_populates="product",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    releases = relationship(
        "Release",
        back_populates="product",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ProductComponent(PychestrateModelBase, SerializableModel):
    """Represents a component of a product that maps to a source repository."""

    __tablename__ = "product_component"

    __table_args__ = (
        UniqueConstraint("prod_id", "comp_name", name="uq_component_product_name"),
    )

    id = Column("comp_id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    name = Column("comp_name", VARCHAR(128), nullable=False)
    description = Column("comp_description", Text, nullable=True)

    product_id = Column(
        "prod_id", BigInteger, ForeignKey("product.prod_id"), nullable=False, index=True
    )
    repository_id = Column(
        "repo_id", BigInteger, ForeignKey("repository.repo_id"), nullable=False, index=True
    )

    product = relationship("Product", back_populates="components", lazy="selectin")
    repository = relationship("Repository", back_populates="components", lazy="selectin")


class ProductToRepository(PychestrateModelBase, SerializableModel):
    """Associates product level repositories such as documentation with a product."""

    __tablename__ = "product_to_repository"

    __table_args__ = (
        UniqueConstraint("prod_id", "repo_id", name="uq_product_repository"),
    )

    id = Column("ptor_id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    product_id = Column(
        "prod_id", BigInteger, ForeignKey("product.prod_id"), nullable=False, index=True
    )
    repository_id = Column(
        "repo_id", BigInteger, ForeignKey("repository.repo_id"), nullable=False, index=True
    )

    product = relationship("Product", back_populates="product_repositories", lazy="selectin")
    repository = relationship("Repository", back_populates="product_links", lazy="selectin")


class ReleaseTrain(PychestrateModelBase, SerializableModel):
    """Represents the symbolic branch structure used to orchestrate a release train."""

    __tablename__ = "release_train"

    id = Column("rtrain_id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    name = Column("rtrain_name", VARCHAR(128), nullable=False, unique=True)
    description = Column("rtrain_description", Text, nullable=True)

    branches = relationship(
        "ReleaseTrainBranch",
        back_populates="train",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    releases = relationship(
        "Release",
        back_populates="release_train",
        lazy="selectin",
    )


class ReleaseTrainBranchType(str, enum.Enum):
    """Enumerates the logical role a symbolic branch plays within a release train."""

    TEAM = "team"
    INTEGRATION = "integration"
    MAINLINE = "mainline"
    SUPPORT = "support"
    OTHER = "other"


class ReleaseTrainBranch(PychestrateModelBase, SerializableModel):
    """Symbolic branches that define the flow of a release train."""

    __tablename__ = "release_train_branch"

    __table_args__ = (
        UniqueConstraint("rtrain_id", "rtbranch_name", name="uq_release_train_branch"),
    )

    id = Column("rtbranch_id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    name = Column("rtbranch_name", VARCHAR(128), nullable=False)
    description = Column("rtbranch_description", Text, nullable=True)
    branch_type = Column(
        "rtbranch_type",
        Enum(ReleaseTrainBranchType, name="release_train_branch_type", native_enum=False),
        nullable=False,
        default=ReleaseTrainBranchType.OTHER,
    )
    display_order = Column("rtbranch_display_order", Integer, nullable=False, default=0)
    is_terminal = Column("rtbranch_is_terminal", Boolean, nullable=False, default=False)
    metadata_payload = Column("rtbranch_metadata", JSON, nullable=True)

    release_train_id = Column(
        "rtrain_id", BigInteger, ForeignKey("release_train.rtrain_id"), nullable=False, index=True
    )
    parent_id = Column(
        "parent_rtbranch_id",
        BigInteger,
        ForeignKey("release_train_branch.rtbranch_id"),
        nullable=True,
        index=True,
    )

    train = relationship("ReleaseTrain", back_populates="branches", lazy="selectin")
    parent = relationship(
        "ReleaseTrainBranch",
        remote_side=lambda: [ReleaseTrainBranch.id],
        backref=backref(
            "children",
            lazy="selectin",
            order_by="ReleaseTrainBranch.display_order",
        ),
        lazy="selectin",
    )

    branch_assignments = relationship(
        "ReleaseBranchAssignment",
        back_populates="symbolic_branch",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class Release(PychestrateModelBase, SerializableModel):
    """Represents a release of a product built from a release train."""

    __tablename__ = "release"

    __table_args__ = (
        UniqueConstraint("prod_id", "release_name", name="uq_release_product_name"),
    )

    id = Column("release_id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    name = Column("release_name", VARCHAR(128), nullable=False)
    description = Column("release_description", Text, nullable=True)
    documentation_url = Column("release_documentation_url", VARCHAR(2048), nullable=True)
    start_date = Column("release_start_date", UtcDateTime(timezone=True), nullable=True)
    release_date = Column("release_release_date", UtcDateTime(timezone=True), nullable=True)

    product_id = Column(
        "prod_id", BigInteger, ForeignKey("product.prod_id"), nullable=False, index=True
    )
    release_train_id = Column(
        "rtrain_id", BigInteger, ForeignKey("release_train.rtrain_id"), nullable=True, index=True
    )

    product = relationship("Product", back_populates="releases", lazy="selectin")
    release_train = relationship("ReleaseTrain", back_populates="releases", lazy="selectin")

    branch_assignments = relationship(
        "ReleaseBranchAssignment",
        back_populates="release",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ReleaseBranchAssignment(PychestrateModelBase, SerializableModel):
    """Maps a symbolic release train branch to a literal branch name for a release."""

    __tablename__ = "release_branch_assignment"

    __table_args__ = (
        UniqueConstraint(
            "release_id",
            "rtbranch_id",
            name="uq_release_branch_assignment",
        ),
    )

    id = Column("rba_id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    literal_branch_name = Column("rba_literal_branch_name", VARCHAR(256), nullable=False)

    release_id = Column(
        "release_id", BigInteger, ForeignKey("release.release_id"), nullable=False, index=True
    )
    release_train_branch_id = Column(
        "rtbranch_id",
        BigInteger,
        ForeignKey("release_train_branch.rtbranch_id"),
        nullable=False,
        index=True,
    )

    release = relationship("Release", back_populates="branch_assignments", lazy="selectin")
    symbolic_branch = relationship("ReleaseTrainBranch", back_populates="branch_assignments", lazy="selectin")


class Repository(PychestrateModelBase, SerializableModel):
    """
        A data modelf for storing repository information.
    """

    __tablename__ = "repository"

    __table_args__ = (UniqueConstraint('repo_name', 'repo_repository', name='uq_repository_name_url'),)

    id = Column('repo_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    name = Column('repo_name', VARCHAR(128), nullable=False)
    url = Column('repo_repository', VARCHAR(2048), nullable=False, unique=True)
    repotype = Column('repo_type', Enum(RepositoryType, name='repository_type', native_enum=False), nullable=False)
    scope = Column('repo_scope', Enum(RepositoryScope, name='repository_scope', native_enum=False), nullable=False)
    repoconf = Column('repo_conf', JSON, nullable=False)
    product_links = relationship('ProductToRepository', back_populates='repository', cascade='all, delete-orphan', lazy='selectin')
    components = relationship('ProductComponent', back_populates='repository', lazy='selectin')
    branches = relationship('Branch', back_populates='repository', cascade='all, delete-orphan', lazy='selectin')


class Branch(PychestrateModelBase, SerializableModel):
    """
        A data model for storing source branch information.
    """

    __tablename__ = "branch"

    __table_args__ = (UniqueConstraint('repo_id', 'branch_name', name='uq_branch_repo_name'),)

    id = Column('branch_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    name = Column('branch_name', VARCHAR(128), nullable=False)
    owner = Column('branch_owner', VARCHAR(128), nullable=False)

    repo_id = Column('repo_id', BigInteger, ForeignKey('repository.repo_id'), nullable=False, index=True)

    repository = relationship('Repository', back_populates='branches', lazy='selectin')

    build_jobs = relationship('BuildJob', back_populates='branch', cascade='all, delete-orphan', lazy='selectin')
    build_results = relationship('BuildResult', back_populates='branch', cascade='all, delete-orphan', lazy='selectin')


class BuildJob(PychestrateModelBase, SerializableModel):
    """
        A data model for storing build job information.
    """

    __tablename__ = "build_job"

    id = Column('bjob_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    name = Column('bjob_name', VARCHAR(128), nullable=False)
    start = Column('bjob_start', UtcDateTime(timezone=True), nullable=False, server_default=func.now())
    stop = Column('bjob_stop', UtcDateTime(timezone=True), nullable=True)
    change = Column('bjob_change', VARCHAR(128), nullable=False)
    status = Column('bjob_status', Enum(WorkPacketStatus, name='build_job_status', native_enum=False), nullable=False, default=WorkPacketStatus.QUEUED)

    branch_id = Column('branch_id', BigInteger, ForeignKey('branch.branch_id'), nullable=False, index=True)

    branch = relationship('Branch', back_populates='build_jobs', lazy='selectin')
    result = relationship('BuildResult', back_populates='job', uselist=False, cascade='all, delete-orphan', lazy='selectin')


class BuildResult(PychestrateModelBase, SerializableModel):
    """
        A data model for storing build information.
    """

    __tablename__ = "build_result"

    id = Column('build_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    name = Column('build_name', VARCHAR(128), nullable=False)
    start = Column('build_start', UtcDateTime(timezone=True), nullable=False, server_default=func.now())
    stop = Column('build_stop', UtcDateTime(timezone=True), nullable=True)
    change = Column('build_change', VARCHAR(128), nullable=False)

    branch_id = Column('branch_id', BigInteger, ForeignKey('branch.branch_id'), nullable=False, index=True)
    job_id = Column('bjob_id', BigInteger, ForeignKey('build_job.bjob_id'), nullable=True, index=True)

    branch = relationship('Branch', back_populates='build_results', lazy='selectin')
    job = relationship('BuildJob', back_populates='result', lazy='selectin')

    byproducts = relationship('BuildByProduct', back_populates='build', cascade='all, delete-orphan', lazy='selectin')


class BuildByProduct(PychestrateModelBase, SerializableModel):
    """
        A data mode for linking build byproducts to build
    """
    __tablename__ = "build_byproduct"

    id = Column('bbp_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    product = Column('bbp_product', VARCHAR(128), nullable=False)
    arch = Column('bbp_arch', VARCHAR(128), nullable=False)
    buildno = Column('bbp_buildno', VARCHAR(128), nullable=False)
    flavor = Column('bbp_flavor', VARCHAR(128), nullable=False)
    result_url = Column('bbp_result_url', VARCHAR(2048), nullable=False)

    build_id = Column('build_id', BigInteger, ForeignKey('build_result.build_id'), nullable=False, index=True)

    build = relationship('BuildResult', back_populates='byproducts', lazy='selectin')


class User(PychestrateModelBase, SerializableModel):
    """
        A data model for the minimal amount of User information to store
        for relating automation data to an enterprise user.
    """

    __tablename__ = 'user'

    id = Column('user_id', UUIDType, primary_key=True, default=uuid.uuid4, server_default=text('gen_random_uuid()'))
    first_name = Column('user_firstName', VARCHAR(40), nullable=False)
    last_name = Column('user_lastName', VARCHAR(40), nullable=False)
    display_name = Column('user_displayName', VARCHAR(128), nullable=True,
                          doc="Display name of the user")
    email = Column('user_email', VARCHAR(128), nullable=False, unique=True)
    login = Column('user_login', VARCHAR(128), nullable=False, unique=True)
    ownertag = Column('user_ownertag', VARCHAR(40), nullable=True)
    status = Column('user_status', VARCHAR(20), nullable=False, default='active',
                    doc="Status of the user account (e.g., 'active', 'inactive')")
    roles = Column('user_roles', VARCHAR(1024), nullable=True,
                   doc="Comma-separated list of roles assigned to the user")
    authtype = Column('user_authtype', VARCHAR(20), nullable=False, default='consumer',
                      doc="Type of user (e.g., 'internal', 'consumer')")
    created_at = Column('user_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the user record was created")
    updated_at = Column('user_updated_at', UtcDateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False,
                        doc="Timestamp when the user record was last updated")

    work_packets = relationship('WorkPacket', back_populates='user', lazy='selectin')

    test_runs = relationship('TestJobRun', back_populates='user', lazy='selectin')

    feature_groups = relationship('FeatureGroupMembership', back_populates='user', lazy='selectin', cascade='all, delete-orphan')


class WorkQueue(PychestrateModelBase, SerializableModel):
    """
        A data model for a
    """
    __tablename__ = 'work_queue'

    id = Column('queue_id', UUIDType, primary_key=True, nullable=False, default=uuid.uuid4, server_default=text('gen_random_uuid()'))
    name = Column('queue_name', String(128), nullable=False, unique=True)
    qtype = Column('queue_type', String(128), nullable=False)
    description = Column('queue_desc', TEXT, nullable=False)
    state = Column('queue_state', Enum(WorkQueueState, name='work_queue_state', native_enum=False), nullable=False)

    packets = relationship('WorkPacket', back_populates='queue', cascade='all, delete-orphan', lazy='selectin')


class WorkPacket(PychestrateModelBase, SerializableModel):
    """
        A data model for a WorkPacket(s) and the work items that are part of a work queue.
    """
    __tablename__ = 'work_packet'
    
    id = Column('wkpack_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)

    jtype = Column('wkpk_jtype', Enum(WorkQueueJobType, name='work_queue_job_type', native_enum=False), nullable=False)
    title =  Column('wkpk_title', String(1024), nullable=False)
    description = Column('wkpk_description', Text, nullable=False)
    branch =  Column('wkpk_branch', String(1024), nullable=True)
    build =  Column('wkpk_build', String(1024), nullable=True)
    flavor =  Column('wkpk_flavor', String(1024), nullable=True)
    ownertag = Column('wkpk_ownertag', VARCHAR(40), nullable=True)
    added = Column('wkpk_added', UtcDateTime(timezone=True), nullable=False, server_default=func.now())
    start = Column('wkpk_start', UtcDateTime(timezone=True), nullable=True)
    stop = Column('wkpk_stop', UtcDateTime(timezone=True), nullable=True)
    progress = Column('wkpk_progress', Float, default=0.0)
    status = Column('wkpk_status', Enum(WorkPacketStatus, name='work_packet_status', native_enum=False), nullable=False, index=True)
    packet = Column('wkpk_packet', TEXT, nullable=False)

    queue_id = Column('queue_id',  UUIDType, ForeignKey('work_queue.queue_id'), nullable=False, index=True)
    user_id = Column('user_id', UUIDType, ForeignKey('user.user_id'), nullable=False, index=True)

    queue = relationship('WorkQueue', back_populates='packets', lazy='selectin')

    user = relationship('User', back_populates='work_packets', lazy='selectin')


class FeatureGroup(PychestrateModelBase, SerializableModel):
    """
        A data model for storing information about feature groups.
    """
    __tablename__ = 'feature_group'
    
    id = Column('fg_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    name = Column('fg_name', VARCHAR(256), nullable=False)
    description = Column('fg_description', TEXT, nullable=False)

    test_jobs = relationship('TestJob', back_populates='owner_feature_group', lazy='selectin')

    memberships = relationship('FeatureGroupMembership', back_populates='feature_group', cascade='all, delete-orphan', lazy='selectin')

    test_runs = relationship('TestJobRun', back_populates='feature_group', lazy='selectin')


class TestJob(PychestrateModelBase, SerializableModel):
    """
        A data model for storing information about test jobs and
        user and feature group associations with a given test job.
    """
    __tablename__ = 'test_job'

    id = Column('tj_id', UUIDType, primary_key=True, default=uuid.uuid4, server_default=text('gen_random_uuid()'))
    title =  Column('tj_title', VARCHAR(1024), nullable=False)
    description = Column('tj_description', Text, nullable=False)

    owner_fg_id = Column('owner_fg_id', BigInteger, ForeignKey('feature_group.fg_id'), nullable=True, index=True)

    owner_feature_group = relationship('FeatureGroup', back_populates='test_jobs', lazy='selectin')

    runs = relationship('TestJobRun', back_populates='job', cascade='all, delete-orphan', lazy='selectin')

    result_containers = relationship('TestResultContainer', back_populates='test_job', cascade='all, delete-orphan', lazy='selectin')


class TestJobRun(PychestrateModelBase, SerializableModel):
    """
        A data model for a TestJob run.
    """

    __tablename__ = 'test_job_run'

    instance = Column('tjr_instance', UUIDType, nullable=False, primary_key=True, default=uuid.uuid4, server_default=text('gen_random_uuid()'))
    branch =  Column('tjr_branch', VARCHAR(1024), nullable=True)
    build =  Column('tjr_build', VARCHAR(1024), nullable=True)
    flavor =  Column('tjr_flavor', VARCHAR(1024), nullable=True)
    ownertag = Column('wkpk_ownertag', UUIDType, nullable=True)
    start = Column('tjr_start', UtcDateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    stop = Column('tjr_stop', UtcDateTime(timezone=True), nullable=True)
    detail = Column('tjr_detail', JSON, nullable=True)

    job_id = Column('job_id', UUIDType, ForeignKey('test_job.tj_id'), nullable=False, index=True)
    user_id = Column('user_id', UUIDType, ForeignKey('user.user_id'), nullable=False, index=True)

    fg_id = Column('fg_id', BigInteger, ForeignKey('feature_group.fg_id'), nullable=True, index=True)

    job = relationship('TestJob', back_populates='runs', lazy='selectin')

    user = relationship('User', back_populates='test_runs', lazy='selectin')

    feature_group = relationship('FeatureGroup', back_populates='test_runs', lazy='selectin')

    results = relationship('TestResult', back_populates='test_run', cascade='all, delete-orphan', lazy='selectin')


class TestResult(PychestrateModelBase, SerializableModel):
    """
        A data model for a TestResult node that is part of a test result tree.
    """
    __tablename__ = 'test_result'

    instance = Column('tstr_instance', UUIDType, nullable=False, primary_key=True, default=uuid.uuid4, server_default=text('gen_random_uuid()'))
    name =  Column('tstr_name', VARCHAR(1024), nullable=False)
    monikers = Column('tstr_monikers', JSON, nullable=True)
    pivots = Column('tstr_pivots', JSON, nullable=True)
    rtype = Column('tstr_rtype', String(50), nullable=False)
    result = Column('tstr_result', String(50), nullable=False)
    start = Column('tstr_start', UtcDateTime(timezone=True), nullable=False, server_default=func.now())
    stop = Column('tstr_stop', UtcDateTime(timezone=True), nullable=True)
    detail = Column('tstr_detail', JSON, nullable=True)

    testrun = Column('tjr_instance', UUIDType, ForeignKey('test_job_run.tjr_instance'), nullable=True, index=True)

    test_run = relationship('TestJobRun', back_populates='results', lazy='selectin')


class TestResultContainer(PychestrateModelBase, SerializableModel):
    """
        A data model for a TestResultContainer node that is part of a test result tree.  The
        TestResultContainer node serves as a parent and container for individual result based
        nodes.
    """
    __tablename__ = 'test_result_container'
    
    id = Column('tstrcont_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    name =  Column('tstrcont_name', VARCHAR(1024), nullable=False)
    instance = Column('tstrcont_instance', UUIDType, nullable=False, default=uuid.uuid4, server_default=text('gen_random_uuid()'))
    parent = Column('tstrcont_parent', UUIDType, nullable=True)
    rtype = Column('tstrcont_rtype', String(50), nullable=False)

    testjob_id = Column('tj_id', UUIDType, ForeignKey('test_job.tj_id'), index=True)

    test_job = relationship('TestJob', back_populates='result_containers', lazy='selectin')


class FeatureGroupMembership(PychestrateModelBase, SerializableModel):
    """
        A data model for associating FeatureGroup(s) to Users(s)
    """
    __tablename__ = "feature_group_membership"

    fg_id = Column('fg_id', BigInteger, ForeignKey('feature_group.fg_id'), primary_key=True, index=True)
    user_id = Column('user_id', UUIDType, ForeignKey('user.user_id'), primary_key=True, index=True)

    join_date = Column('fgm_join_date', UtcDateTime(timezone=True), nullable=False, server_default=func.now())
    departure_date = Column('fgm_departure_date', UtcDateTime(timezone=True), nullable=True)

    feature_group = relationship('FeatureGroup', back_populates='memberships', lazy='selectin')

    user = relationship('User', back_populates='feature_groups', lazy='selectin')


# =============================================================================
# System Configuration Models
# =============================================================================

# Association table for role-permission many-to-many relationship
role_permissions = Table(
    'role_permissions',
    PychestrateModelBase.metadata,
    Column('role_id', BigInteger, ForeignKey('system_roles.role_id'), primary_key=True),
    Column('permission_id', BigInteger, ForeignKey('permissions.perm_id'), primary_key=True)
)


class Permission(PychestrateModelBase, SerializableModel):
    """
        A data model for storing permission definitions.
        Permissions represent specific actions that can be allowed or denied.
    """
    __tablename__ = 'permissions'

    id = Column('perm_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    name = Column('perm_name', VARCHAR(64), unique=True, nullable=False, index=True,
                  doc="Permission name in format 'resource.action' (e.g., 'users.create', 'users.read')")
    description = Column('perm_description', VARCHAR(255), nullable=True,
                         doc="Human-readable description of what this permission allows")

    roles = relationship('SystemRole', secondary=role_permissions, back_populates='permissions', lazy='selectin')


class SystemRole(PychestrateModelBase, SerializableModel):
    """
        A data model for storing system role definitions.
        System roles extend the base Role concept with permission associations
        and a flag to indicate system-defined roles that cannot be deleted.
    """
    __tablename__ = 'system_roles'

    id = Column('role_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    name = Column('role_name', VARCHAR(64), unique=True, nullable=False, index=True,
                  doc="Unique name for the role (e.g., 'Administrator', 'Operator', 'Viewer')")
    description = Column('role_description', VARCHAR(255), nullable=True,
                         doc="Human-readable description of the role's purpose")
    is_system = Column('role_is_system', Boolean, default=False, nullable=False,
                       doc="Flag indicating if this is a system-defined role that cannot be deleted")
    created_at = Column('role_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the role was created")

    permissions = relationship('Permission', secondary=role_permissions, back_populates='roles', lazy='selectin')


class Session(PychestrateModelBase, SerializableModel):
    """
        A data model for tracking authenticated user sessions.
        Sessions store authentication tokens and metadata for session management.
    """
    __tablename__ = 'sessions'

    id = Column('sess_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    token = Column('sess_token', VARCHAR(64), unique=True, nullable=False, index=True,
                   doc="Unique session token used for authentication")
    user_id = Column('sess_user_id', UUIDType, ForeignKey('user.user_id'), nullable=False, index=True,
                     doc="Reference to the authenticated user")
    created_at = Column('sess_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the session was created")
    expires_at = Column('sess_expires_at', UtcDateTime(timezone=True), nullable=False,
                        doc="Timestamp when the session expires")
    last_activity = Column('sess_last_activity', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                           doc="Timestamp of the last activity in this session")
    client_ip = Column('sess_client_ip', VARCHAR(45), nullable=True,
                       doc="IP address of the client (supports IPv6)")
    user_agent = Column('sess_user_agent', VARCHAR(255), nullable=True,
                        doc="User agent string from the client browser")
    csrf_token = Column('sess_csrf_token', VARCHAR(64), nullable=True,
                        doc="CSRF token associated with this session")


class PasswordHistory(PychestrateModelBase, SerializableModel):
    """
        A data model for tracking password history to prevent password reuse.
        Stores the last N password hashes for each user.
    """
    __tablename__ = 'password_history'

    id = Column('pwdhist_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    user_id = Column('pwdhist_user_id', UUIDType, ForeignKey('user.user_id'), nullable=False, index=True,
                     doc="Reference to the user whose password history this is")
    password_hash = Column('pwdhist_password_hash', VARCHAR(255), nullable=False,
                           doc="Hashed password value (bcrypt or argon2)")
    created_at = Column('pwdhist_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when this password was set")


class VariableType(str, enum.Enum):
    """
        Enum-like class to represent the supported types for variables.
    """
    STRING = 'string'
    INTEGER = 'integer'
    FLOAT = 'float'
    BOOLEAN = 'boolean'
    JSON = 'json'


class AuditEventType(str, enum.Enum):
    """
        Enum-like class to represent the types of audit events.
    """
    AUTH_SUCCESS = 'auth_success'
    AUTH_FAILURE = 'auth_failure'
    LOGOUT = 'logout'
    USER_CREATED = 'user_created'
    USER_UPDATED = 'user_updated'
    USER_DEACTIVATED = 'user_deactivated'
    ROLE_ASSIGNED = 'role_assigned'
    ROLE_REMOVED = 'role_removed'
    PASSWORD_CHANGED = 'password_changed'
    PASSWORD_RESET_REQUESTED = 'password_reset_requested'
    PASSWORD_RESET_COMPLETED = 'password_reset_completed'
    VARIABLE_CREATED = 'variable_created'
    VARIABLE_UPDATED = 'variable_updated'
    VARIABLE_DELETED = 'variable_deleted'
    SESSION_TERMINATED = 'session_terminated'
    SECRET_CREATED = 'secret_created'
    SECRET_UPDATED = 'secret_updated'
    SECRET_DELETED = 'secret_deleted'
    SECRET_ACCESSED = 'secret_accessed'
    SCOPE_CREATED = 'scope_created'
    SCOPE_DELETED = 'scope_deleted'


class PasswordResetToken(PychestrateModelBase, SerializableModel):
    """
        A data model for storing password reset tokens.
        Tokens are time-limited and single-use for security.
    """
    __tablename__ = 'password_reset_tokens'

    id = Column('prt_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    user_id = Column('prt_user_id', UUIDType, ForeignKey('user.user_id'), nullable=False, index=True,
                     doc="Reference to the user requesting password reset")
    token = Column('prt_token', VARCHAR(64), unique=True, nullable=False, index=True,
                   doc="Unique reset token")
    created_at = Column('prt_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the token was created")
    expires_at = Column('prt_expires_at', UtcDateTime(timezone=True), nullable=False,
                        doc="Timestamp when the token expires")
    used = Column('prt_used', Boolean, default=False, nullable=False,
                  doc="Flag indicating if the token has been used")


class AuditLog(PychestrateModelBase, SerializableModel):
    """
        A data model for recording security-relevant audit events.
        Provides a comprehensive audit trail for compliance and investigation.
    """
    __tablename__ = 'audit_logs'

    id = Column('audit_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    event_type = Column('audit_event_type', VARCHAR(64), nullable=False, index=True,
                        doc="Type of audit event")
    timestamp = Column('audit_timestamp', UtcDateTime(timezone=True), default=utc_now, nullable=False, index=True,
                       doc="Timestamp when the event occurred")
    user_id = Column('audit_user_id', VARCHAR(40), nullable=True,
                     doc="ID of the user who performed the action")
    username = Column('audit_username', VARCHAR(64), nullable=True,
                      doc="Username of the user who performed the action")
    target_user_id = Column('audit_target_user_id', VARCHAR(40), nullable=True,
                            doc="ID of the user affected by the action")
    target_username = Column('audit_target_username', VARCHAR(64), nullable=True,
                             doc="Username of the user affected by the action")
    client_ip = Column('audit_client_ip', VARCHAR(45), nullable=True,
                       doc="IP address of the client (supports IPv6)")
    details_json = Column('audit_details_json', Text, nullable=True,
                          doc="JSON-encoded additional details about the event")


# =============================================================================
# Resource Management Models
# =============================================================================

class ResourceType(str, enum.Enum):
    """
        Enum-like class to represent the types of resources that can be managed.
    """
    DEVICE = 'device'
    IP_ADDRESS = 'ip_address'
    PORT = 'port'
    CREDENTIAL = 'credential'
    GENERIC = 'generic'


class HealthStatus(str, enum.Enum):
    """
        Enum-like class to represent the health status of a resource.
    """
    ONLINE = 'online'
    OFFLINE = 'offline'
    DEGRADED = 'degraded'
    MAINTENANCE = 'maintenance'


class AllocationMode(str, enum.Enum):
    """
        Enum-like class to represent the allocation mode for resource checkout.
    """
    EXCLUSIVE = 'exclusive'
    SHARED = 'shared'


class AllocationStatus(str, enum.Enum):
    """
        Enum-like class to represent the status of a resource allocation.
    """
    ACTIVE = 'active'
    RELEASED = 'released'
    EXPIRED = 'expired'
    FORCED = 'forced'


class ReservationStatus(str, enum.Enum):
    """
        Enum-like class to represent the status of a resource reservation.
    """
    PENDING = 'pending'
    ACTIVE = 'active'
    COMPLETED = 'completed'
    CANCELLED = 'cancelled'


class IPAllocationStatus(str, enum.Enum):
    """
        Enum-like class to represent the status of an IP address allocation.
    """
    ACTIVE = 'active'
    RELEASED = 'released'
    EXPIRED = 'expired'


class IPVersion(str, enum.Enum):
    """
        Enum-like class to represent the IP version.
    """
    IPV4 = 'ipv4'
    IPV6 = 'ipv6'


# Association table for resource-tag many-to-many relationship
resource_tags = Table(
    'resource_tags',
    PychestrateModelBase.metadata,
    Column('resource_id', BigInteger, ForeignKey('resources.res_id'), primary_key=True),
    Column('tag_id', BigInteger, ForeignKey('resource_tags_def.tag_id'), primary_key=True)
)


# Association table for pool-role permissions
pool_permissions = Table(
    'pool_permissions',
    PychestrateModelBase.metadata,
    Column('pool_id', BigInteger, ForeignKey('resource_pools.pool_id'), primary_key=True),
    Column('role_id', BigInteger, ForeignKey('system_roles.role_id'), primary_key=True),
    Column('can_view', Boolean, default=True, nullable=False),
    Column('can_checkout', Boolean, default=False, nullable=False),
    Column('can_manage', Boolean, default=False, nullable=False)
)


class ResourcePool(PychestrateModelBase, SerializableModel):
    """
        A data model for organizing resources into logical pools for access control
        and grouping related resources together.
    """
    __tablename__ = 'resource_pools'

    id = Column('pool_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    name = Column('pool_name', VARCHAR(128), unique=True, nullable=False, index=True,
                  doc="Unique name for the resource pool")
    description = Column('pool_description', VARCHAR(512), nullable=True,
                         doc="Human-readable description of the pool's purpose")
    is_default = Column('pool_is_default', Boolean, default=False, nullable=False,
                        doc="Flag indicating if this is the default pool for unassigned resources")
    created_at = Column('pool_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the pool was created")
    created_by_id = Column('pool_created_by_id', UUIDType, ForeignKey('user.user_id'), nullable=True,
                           doc="Reference to the user who created this pool")

    resources = relationship('Resource', back_populates='pool', lazy='selectin')


class Tag(PychestrateModelBase, SerializableModel):
    """
        A data model for storing resource tags used for filtering and organization.
        Tags can be applied to multiple resources for categorization.
    """
    __tablename__ = 'resource_tags_def'

    id = Column('tag_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    name = Column('tag_name', VARCHAR(64), unique=True, nullable=False, index=True,
                  doc="Unique name for the tag (alphanumeric, underscores, hyphens only)")
    description = Column('tag_description', VARCHAR(255), nullable=True,
                         doc="Human-readable description of the tag's purpose")
    created_at = Column('tag_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the tag was created")

    resources = relationship('Resource', secondary=resource_tags, back_populates='tags', lazy='selectin')



class Resource(PychestrateModelBase, SerializableModel):
    """
        A data model for storing resource definitions that can be allocated to jobs or users.
        Resources include physical devices, IP addresses, ports, credentials, and other assets.
    """
    __tablename__ = 'resources'

    __table_args__ = (
        Index('ix_resources_pool_name', 'res_pool_id', 'res_name', unique=True),
    )

    id = Column('res_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    name = Column('res_name', VARCHAR(128), nullable=False, index=True,
                  doc="Name of the resource (unique within pool)")
    resource_type = Column('res_type', VARCHAR(32), nullable=False,
                           doc="Type of resource (device, ip_address, port, credential, generic)")
    pool_id = Column('res_pool_id', BigInteger, ForeignKey('resource_pools.pool_id'), nullable=True, index=True,
                     doc="Reference to the pool containing this resource")
    description = Column('res_description', VARCHAR(512), nullable=True,
                         doc="Human-readable description of the resource")
    metadata_json = Column('res_metadata_json', JSON, default={}, nullable=False,
                           doc="JSON-encoded metadata for the resource")
    sensitive_fields = Column('res_sensitive_fields', JSON, default=[], nullable=False,
                              doc="List of metadata keys that should be masked in non-privileged responses")
    capacity = Column('res_capacity', Integer, default=1, nullable=False,
                      doc="Number of concurrent allocations allowed for shared resources")
    health_status = Column('res_health_status', VARCHAR(32), default='online', nullable=False,
                           doc="Current health status (online, offline, degraded, maintenance)")
    created_at = Column('res_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the resource was created")
    updated_at = Column('res_updated_at', UtcDateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False,
                        doc="Timestamp when the resource was last updated")
    created_by_id = Column('res_created_by_id', UUIDType, ForeignKey('user.user_id'), nullable=True,
                           doc="Reference to the user who created this resource")

    pool = relationship('ResourcePool', back_populates='resources', lazy='selectin')
    tags = relationship('Tag', secondary=resource_tags, back_populates='resources', lazy='selectin')
    allocations = relationship('Allocation', back_populates='resource', lazy='selectin')
    reservations = relationship('Reservation', back_populates='resource', lazy='selectin')
    health_check_config = relationship('HealthCheckConfig', back_populates='resource', uselist=False, lazy='selectin')
    health_transitions = relationship('HealthTransitionLog', back_populates='resource', lazy='selectin')
    metadata_history = relationship('ResourceMetadataHistory', back_populates='resource', lazy='selectin')



class IPPool(PychestrateModelBase, SerializableModel):
    """
        A data model for storing IP address pools with CIDR ranges.
        IP pools allow dynamic allocation of IP addresses to orchestration jobs.
    """
    __tablename__ = 'ip_pools'

    id = Column('ippool_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    name = Column('ippool_name', VARCHAR(128), unique=True, nullable=False, index=True,
                  doc="Unique name for the IP pool")
    cidr = Column('ippool_cidr', VARCHAR(64), nullable=False,
                  doc="CIDR notation for the IP range (e.g., '192.168.1.0/24')")
    ip_version = Column('ippool_ip_version', VARCHAR(8), nullable=False,
                        doc="IP version (ipv4 or ipv6)")
    network_address = Column('ippool_network_address', VARCHAR(64), nullable=False,
                             doc="Network address calculated from CIDR")
    broadcast_address = Column('ippool_broadcast_address', VARCHAR(64), nullable=True,
                               doc="Broadcast address calculated from CIDR (IPv4 only)")
    subnet_mask = Column('ippool_subnet_mask', VARCHAR(64), nullable=False,
                         doc="Subnet mask (e.g., '255.255.255.0')")
    gateway = Column('ippool_gateway', VARCHAR(64), nullable=True,
                     doc="Default gateway for the IP pool")
    dns_servers = Column('ippool_dns_servers', JSON, default=[], nullable=False,
                         doc="List of DNS server addresses")
    description = Column('ippool_description', VARCHAR(512), nullable=True,
                         doc="Human-readable description of the IP pool")
    reserved_ips = Column('ippool_reserved_ips', JSON, default=[], nullable=False,
                          doc="List of IP addresses excluded from allocation")
    created_at = Column('ippool_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the IP pool was created")
    created_by_id = Column('ippool_created_by_id', UUIDType, ForeignKey('user.user_id'), nullable=True,
                           doc="Reference to the user who created this IP pool")

    allocations = relationship('IPAllocation', back_populates='pool', lazy='selectin')


class IPAllocation(PychestrateModelBase, SerializableModel):
    """
        A data model for tracking IP address allocations from IP pools.
        Each allocation represents a single IP address assigned to a job or user.
    """
    __tablename__ = 'ip_allocations'

    __table_args__ = (
        Index('ix_ip_allocations_pool_ip', 'ipalloc_pool_id', 'ipalloc_ip_address'),
        Index('ix_ip_allocations_pool_status', 'ipalloc_pool_id', 'ipalloc_status'),
        Index('ix_ip_allocations_job', 'ipalloc_job_id'),
    )

    id = Column('ipalloc_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    pool_id = Column('ipalloc_pool_id', BigInteger, ForeignKey('ip_pools.ippool_id'), nullable=False, index=True,
                     doc="Reference to the IP pool")
    ip_address = Column('ipalloc_ip_address', VARCHAR(64), nullable=False,
                        doc="The allocated IP address")
    user_id = Column('ipalloc_user_id', UUIDType, ForeignKey('user.user_id'), nullable=False, index=True,
                     doc="Reference to the user who allocated this IP")
    job_id = Column('ipalloc_job_id', VARCHAR(128), nullable=True, index=True,
                    doc="Identifier of the job using this IP")
    status = Column('ipalloc_status', VARCHAR(16), default='active', nullable=False,
                    doc="Allocation status (active, released, expired)")
    checkout_time = Column('ipalloc_checkout_time', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                           doc="Timestamp when the IP was allocated")
    expected_checkin = Column('ipalloc_expected_checkin', UtcDateTime(timezone=True), nullable=True,
                              doc="Expected time for IP release (for timeout)")
    actual_checkin = Column('ipalloc_actual_checkin', UtcDateTime(timezone=True), nullable=True,
                            doc="Actual time when the IP was released")
    reason = Column('ipalloc_reason', VARCHAR(512), nullable=True,
                    doc="Reason for the allocation")

    pool = relationship('IPPool', back_populates='allocations', lazy='selectin')



class Allocation(PychestrateModelBase, SerializableModel):
    """
        A data model for tracking resource allocations (checkouts).
        Allocations link resources to users and jobs with timing and mode information.
    """
    __tablename__ = 'allocations'

    __table_args__ = (
        Index('ix_allocations_resource_status', 'alloc_resource_id', 'alloc_status'),
        Index('ix_allocations_user_status', 'alloc_user_id', 'alloc_status'),
        Index('ix_allocations_job', 'alloc_job_id'),
    )

    id = Column('alloc_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    resource_id = Column('alloc_resource_id', BigInteger, ForeignKey('resources.res_id'), nullable=False, index=True,
                         doc="Reference to the allocated resource")
    user_id = Column('alloc_user_id', UUIDType, ForeignKey('user.user_id'), nullable=False, index=True,
                     doc="Reference to the user who allocated this resource")
    job_id = Column('alloc_job_id', VARCHAR(128), nullable=True, index=True,
                    doc="Identifier of the job using this resource")
    mode = Column('alloc_mode', VARCHAR(16), default='exclusive', nullable=False,
                  doc="Allocation mode (exclusive or shared)")
    status = Column('alloc_status', VARCHAR(16), default='active', nullable=False,
                    doc="Allocation status (active, released, expired, forced)")
    checkout_time = Column('alloc_checkout_time', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                           doc="Timestamp when the resource was allocated")
    expected_checkin = Column('alloc_expected_checkin', UtcDateTime(timezone=True), nullable=True,
                              doc="Expected time for resource release (for timeout)")
    actual_checkin = Column('alloc_actual_checkin', UtcDateTime(timezone=True), nullable=True,
                            doc="Actual time when the resource was released")
    duration_minutes = Column('alloc_duration_minutes', Integer, nullable=True,
                              doc="Total allocation duration in minutes")
    reason = Column('alloc_reason', VARCHAR(512), nullable=True,
                    doc="Reason for the allocation")
    forced_by_id = Column('alloc_forced_by_id', UUIDType, ForeignKey('user.user_id'), nullable=True,
                          doc="Reference to the admin who forced checkin")
    force_reason = Column('alloc_force_reason', VARCHAR(512), nullable=True,
                          doc="Reason for forced checkin")
    metadata_snapshot = Column('alloc_metadata_snapshot', JSON, default={}, nullable=False,
                               doc="Snapshot of resource metadata at checkout time")

    resource = relationship('Resource', back_populates='allocations', lazy='selectin')


class Reservation(PychestrateModelBase, SerializableModel):
    """
        A data model for tracking future resource reservations.
        Reservations allow scheduling resource access for specific time windows.
    """
    __tablename__ = 'reservations'

    __table_args__ = (
        Index('ix_reservations_resource_time', 'resv_resource_id', 'resv_start_time', 'resv_end_time'),
        Index('ix_reservations_job', 'resv_job_id'),
    )

    id = Column('resv_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    resource_id = Column('resv_resource_id', BigInteger, ForeignKey('resources.res_id'), nullable=False, index=True,
                         doc="Reference to the reserved resource")
    user_id = Column('resv_user_id', UUIDType, ForeignKey('user.user_id'), nullable=False, index=True,
                     doc="Reference to the user who made the reservation")
    job_id = Column('resv_job_id', VARCHAR(128), nullable=True, index=True,
                    doc="Identifier of the job for this reservation")
    start_time = Column('resv_start_time', UtcDateTime(timezone=True), nullable=False,
                        doc="Start time of the reservation window")
    end_time = Column('resv_end_time', UtcDateTime(timezone=True), nullable=False,
                      doc="End time of the reservation window")
    mode = Column('resv_mode', VARCHAR(16), default='exclusive', nullable=False,
                  doc="Reservation mode (exclusive or shared)")
    status = Column('resv_status', VARCHAR(16), default='pending', nullable=False,
                    doc="Reservation status (pending, active, completed, cancelled)")
    reason = Column('resv_reason', VARCHAR(512), nullable=True,
                    doc="Reason for the reservation")
    created_at = Column('resv_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the reservation was created")
    allocation_id = Column('resv_allocation_id', BigInteger, ForeignKey('allocations.alloc_id'), nullable=True,
                           doc="Reference to the allocation when reservation is activated")

    resource = relationship('Resource', back_populates='reservations', lazy='selectin')



class HealthCheckConfig(PychestrateModelBase, SerializableModel):
    """
        A data model for storing health check configuration for resources.
        Defines how automated health checks should be performed.
    """
    __tablename__ = 'health_check_configs'

    id = Column('hcc_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    resource_id = Column('hcc_resource_id', BigInteger, ForeignKey('resources.res_id'), unique=True, nullable=False, index=True,
                         doc="Reference to the resource being monitored")
    probe_url = Column('hcc_probe_url', VARCHAR(512), nullable=True,
                       doc="URL endpoint for HTTP health probe")
    probe_command = Column('hcc_probe_command', VARCHAR(1024), nullable=True,
                           doc="Command to execute for health check")
    interval_seconds = Column('hcc_interval_seconds', Integer, default=60, nullable=False,
                              doc="Interval between health checks in seconds")
    timeout_seconds = Column('hcc_timeout_seconds', Integer, default=10, nullable=False,
                             doc="Timeout for health check in seconds")
    failure_threshold = Column('hcc_failure_threshold', Integer, default=3, nullable=False,
                               doc="Number of consecutive failures before marking unhealthy")
    success_threshold = Column('hcc_success_threshold', Integer, default=1, nullable=False,
                               doc="Number of consecutive successes before marking healthy")
    consecutive_failures = Column('hcc_consecutive_failures', Integer, default=0, nullable=False,
                                  doc="Current count of consecutive failures")
    consecutive_successes = Column('hcc_consecutive_successes', Integer, default=0, nullable=False,
                                   doc="Current count of consecutive successes")
    last_check_time = Column('hcc_last_check_time', UtcDateTime(timezone=True), nullable=True,
                             doc="Timestamp of the last health check")
    last_check_result = Column('hcc_last_check_result', Boolean, nullable=True,
                               doc="Result of the last health check (True=healthy)")
    check_requested_at = Column('hcc_check_requested_at', UtcDateTime(timezone=True), nullable=True,
                                doc="When a person asked for a check to run now; the housekeeping worker runs it and clears this")
    last_check_message = Column('hcc_last_check_message', VARCHAR(512), nullable=True,
                                doc="Why the last check failed or was not run (None when it passed)")
    enabled = Column('hcc_enabled', Boolean, default=True, nullable=False,
                     doc="Flag indicating if health checks are enabled")

    resource = relationship('Resource', back_populates='health_check_config', lazy='selectin')


class HealthTransitionLog(PychestrateModelBase, SerializableModel):
    """
        A data model for tracking health status transitions for resources.
        Provides an audit trail of health status changes.
    """
    __tablename__ = 'health_transition_logs'

    __table_args__ = (
        Index('ix_health_transition_logs_resource_time', 'htl_resource_id', 'htl_timestamp'),
    )

    id = Column('htl_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    resource_id = Column('htl_resource_id', BigInteger, ForeignKey('resources.res_id'), nullable=False, index=True,
                         doc="Reference to the resource")
    old_status = Column('htl_old_status', VARCHAR(32), nullable=False,
                        doc="Previous health status")
    new_status = Column('htl_new_status', VARCHAR(32), nullable=False,
                        doc="New health status")
    reason = Column('htl_reason', VARCHAR(512), nullable=True,
                    doc="Reason for the status change")
    triggered_by = Column('htl_triggered_by', VARCHAR(32), nullable=False,
                          doc="What triggered the change (user, health_check, system)")
    user_id = Column('htl_user_id', UUIDType, ForeignKey('user.user_id'), nullable=True,
                     doc="Reference to the user who triggered the change (if applicable)")
    timestamp = Column('htl_timestamp', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                       doc="Timestamp when the transition occurred")

    resource = relationship('Resource', back_populates='health_transitions', lazy='selectin')


class ResourceMetadataHistory(PychestrateModelBase, SerializableModel):
    """
        A data model for tracking changes to resource metadata.
        Provides an audit trail of all metadata modifications.
    """
    __tablename__ = 'resource_metadata_history'

    __table_args__ = (
        Index('ix_resource_metadata_history_resource_time', 'rmh_resource_id', 'rmh_changed_at'),
    )

    id = Column('rmh_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    resource_id = Column('rmh_resource_id', BigInteger, ForeignKey('resources.res_id'), nullable=False, index=True,
                         doc="Reference to the resource")
    old_metadata_json = Column('rmh_old_metadata_json', JSON, nullable=True,
                               doc="Previous metadata value")
    new_metadata_json = Column('rmh_new_metadata_json', JSON, nullable=True,
                               doc="New metadata value")
    changed_by_id = Column('rmh_changed_by_id', UUIDType, ForeignKey('user.user_id'), nullable=True,
                           doc="Reference to the user who made the change")
    changed_at = Column('rmh_changed_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the change was made")

    resource = relationship('Resource', back_populates='metadata_history', lazy='selectin')


# =============================================================================
# Project Management Models
# =============================================================================

class ProjectRole(str, enum.Enum):
    """
        Enum-like class to represent the roles a user can have within a project.
    """
    OWNER = 'owner'
    ADMINISTRATOR = 'administrator'
    DEVELOPER = 'developer'
    VIEWER = 'viewer'


# Association table for project-resource assignments
project_resources = Table(
    'project_resources',
    PychestrateModelBase.metadata,
    Column('proj_id', BigInteger, ForeignKey('projects.proj_id'), primary_key=True),
    Column('res_id', BigInteger, ForeignKey('resources.res_id'), primary_key=True),
    Column('assigned_at', UtcDateTime(timezone=True), default=utc_now, nullable=False),
    Column('assigned_by_id', UUIDType, ForeignKey('user.user_id'), nullable=True)
)


class Project(PychestrateModelBase, SerializableModel):
    """
        A data model for storing project definitions.
        Projects serve as containers for organizing orchestration work including
        repositories, build specifications, infrastructure specifications, test
        specifications, releases, and their associated jobs.
    """
    __tablename__ = 'projects'

    # Project ids must never be reused: RPA specifications and jobs
    # (and the Layer-5 project UUID derived from the id) refer to a
    # project by id without a foreign key, so a reused id would hand a
    # deleted project's rows to a new project. PostgreSQL sequences
    # never reuse values; on SQLite the id is a rowid alias, which
    # reuses the highest deleted id unless the table is AUTOINCREMENT.
    __table_args__ = {'sqlite_autoincrement': True}

    id = Column('proj_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    name = Column('proj_name', VARCHAR(128), unique=True, nullable=False, index=True,
                  doc="Unique name for the project (alphanumeric, underscores, hyphens, periods)")
    description = Column('proj_description', Text, nullable=True,
                         doc="Human-readable description of the project")
    owner_id = Column('proj_owner_id', UUIDType, ForeignKey('user.user_id'), nullable=False, index=True,
                      doc="Reference to the user who owns this project")
    metadata_json = Column('proj_metadata_json', JSON, default={}, nullable=False,
                           doc="JSON-encoded metadata for the project")
    created_at = Column('proj_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the project was created")
    updated_at = Column('proj_updated_at', UtcDateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False,
                        doc="Timestamp when the project was last updated")
    last_activity_at = Column('proj_last_activity_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                              doc="Timestamp of the last activity in this project")

    # Relationships
    members = relationship('ProjectMember', back_populates='project', cascade='all, delete-orphan', lazy='selectin')
    variables = relationship('ProjectVariable', back_populates='project', cascade='all, delete-orphan', lazy='selectin')
    assigned_resources = relationship('Resource', secondary=project_resources, lazy='selectin')
    repositories = relationship('ProjectRepository', back_populates='project', cascade='all, delete-orphan', lazy='selectin')
    build_specs = relationship('ProjectBuildSpec', back_populates='project', cascade='all, delete-orphan', lazy='selectin')
    infra_specs = relationship('ProjectInfraSpec', back_populates='project', cascade='all, delete-orphan', lazy='selectin')
    test_specs = relationship('ProjectTestSpec', back_populates='project', cascade='all, delete-orphan', lazy='selectin')
    release_pipelines = relationship('ProjectReleasePipeline', back_populates='project', cascade='all, delete-orphan', lazy='selectin')
    releases = relationship('ProjectRelease', back_populates='project', cascade='all, delete-orphan', lazy='selectin')
    release_channels = relationship('ProjectReleaseChannel', back_populates='project', cascade='all, delete-orphan', lazy='selectin')
    release_templates = relationship('ProjectReleaseTemplate', back_populates='project', cascade='all, delete-orphan', lazy='selectin')
    watches = relationship('ProjectWatch', back_populates='project', cascade='all, delete-orphan', lazy='selectin')


class ProjectMember(PychestrateModelBase, SerializableModel):
    """
        A data model for storing project membership information.
        Associates users with projects and defines their role within the project.
    """
    __tablename__ = 'project_members'

    __table_args__ = (
        UniqueConstraint('proj_id', 'user_id', name='uq_project_member'),
        Index('ix_project_members_project_user', 'proj_id', 'user_id'),
    )

    id = Column('pm_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    project_id = Column('proj_id', BigInteger, ForeignKey('projects.proj_id'), nullable=False, index=True,
                        doc="Reference to the project")
    user_id = Column('user_id', UUIDType, ForeignKey('user.user_id'), nullable=False, index=True,
                     doc="Reference to the user")
    role = Column('pm_role', VARCHAR(32), nullable=False,
                  doc="Role of the user in the project (owner, administrator, developer, viewer)")
    joined_at = Column('pm_joined_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                       doc="Timestamp when the user joined the project")

    project = relationship('Project', back_populates='members', lazy='selectin')


class ProjectVariable(PychestrateModelBase, SerializableModel):
    """
        A data model for storing project-level variables.
        Variables can be used in specifications and are resolved before global variables.
    """
    __tablename__ = 'project_variables'

    __table_args__ = (
        UniqueConstraint('proj_id', 'pvar_name', name='uq_project_variable_name'),
        Index('ix_project_variables_project_name', 'proj_id', 'pvar_name'),
    )

    id = Column('pvar_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    project_id = Column('proj_id', BigInteger, ForeignKey('projects.proj_id'), nullable=False, index=True,
                        doc="Reference to the project")
    name = Column('pvar_name', VARCHAR(128), nullable=False,
                  doc="Name of the variable (unique within project)")
    value_json = Column('pvar_value_json', Text, nullable=False,
                        doc="JSON-encoded value of the variable")
    var_type = Column('pvar_type', VARCHAR(16), nullable=False,
                      doc="Type of the variable (string, integer, float, boolean, json)")
    is_sensitive = Column('pvar_is_sensitive', Boolean, default=False, nullable=False,
                          doc="Flag indicating if the variable should be masked in logs and UI")
    description = Column('pvar_description', VARCHAR(512), nullable=True,
                         doc="Human-readable description of the variable's purpose")
    created_at = Column('pvar_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the variable was created")
    updated_at = Column('pvar_updated_at', UtcDateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False,
                        doc="Timestamp when the variable was last updated")

    project = relationship('Project', back_populates='variables', lazy='selectin')



class ProjectRepositoryAuthType(str, enum.Enum):
    """
        Enum-like class to represent the authentication types for project repositories.
    """
    HTTPS_TOKEN = 'https_token'
    SSH_KEY = 'ssh_key'
    NONE = 'none'


class ProjectRepository(PychestrateModelBase, SerializableModel):
    """
        A data model for storing project repository associations.
        Repositories are source code repositories (Git) tracked by the project.
    """
    __tablename__ = 'project_repositories'

    __table_args__ = (
        UniqueConstraint('proj_id', 'prepo_name', name='uq_project_repository_name'),
        Index('ix_project_repositories_project_name', 'proj_id', 'prepo_name'),
    )

    id = Column('prepo_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    project_id = Column('proj_id', BigInteger, ForeignKey('projects.proj_id'), nullable=False, index=True,
                        doc="Reference to the project")
    name = Column('prepo_name', VARCHAR(128), nullable=False,
                  doc="Name of the repository (unique within project)")
    url = Column('prepo_url', VARCHAR(2048), nullable=False,
                 doc="URL of the repository")
    auth_type = Column('prepo_auth_type', VARCHAR(32), nullable=False,
                       doc="Authentication type (https_token, ssh_key, none)")
    credential_secret_ref = Column('prepo_credential_secret_ref', VARCHAR(256), nullable=True,
                                   doc="Reference to secret in Secret_Manager for credentials")
    default_branch = Column('prepo_default_branch', VARCHAR(128), default='main', nullable=False,
                            doc="Default branch for the repository")
    description = Column('prepo_description', VARCHAR(512), nullable=True,
                         doc="Human-readable description of the repository")
    last_commit_sha = Column('prepo_last_commit_sha', VARCHAR(64), nullable=True,
                             doc="SHA of the last known commit")
    last_commit_message = Column('prepo_last_commit_message', VARCHAR(512), nullable=True,
                                 doc="Message of the last known commit")
    last_commit_author = Column('prepo_last_commit_author', VARCHAR(128), nullable=True,
                                doc="Author of the last known commit")
    last_commit_time = Column('prepo_last_commit_time', UtcDateTime(timezone=True), nullable=True,
                              doc="Timestamp of the last known commit")
    last_fetch_time = Column('prepo_last_fetch_time', UtcDateTime(timezone=True), nullable=True,
                             doc="Timestamp of the last fetch operation")
    created_at = Column('prepo_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the repository was added")

    project = relationship('Project', back_populates='repositories', lazy='selectin')
    build_specs = relationship('ProjectBuildSpec', back_populates='repository', lazy='selectin')
    watches = relationship('ProjectWatch', back_populates='repository', lazy='selectin')
    release_branches = relationship('ProjectReleaseBranch', back_populates='repository', lazy='selectin')
    merge_events = relationship('ProjectMergeEvent', back_populates='repository', lazy='selectin')
    pull_events = relationship('ProjectPullEvent', back_populates='repository', lazy='selectin')


class ProjectRepositoryRef(PychestrateModelBase, SerializableModel):
    """
        The branches and tags of a project repository as last seen by a
        fetch. Comparing a fetch with these rows is how new commits,
        branches and tags are detected (and repository watches fired).
    """
    __tablename__ = 'project_repository_refs'

    __table_args__ = (
        UniqueConstraint('prepo_id', 'prref_kind', 'prref_name', name='uq_project_repository_ref'),
    )

    id = Column('prref_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    repository_id = Column('prepo_id', BigInteger, ForeignKey('project_repositories.prepo_id'), nullable=False,
                           index=True, doc="Reference to the repository")
    kind = Column('prref_kind', VARCHAR(16), nullable=False,
                  doc="Kind of ref (branch, tag)")
    name = Column('prref_name', VARCHAR(255), nullable=False,
                  doc="Branch or tag name, without the refs/heads/ or refs/tags/ prefix")
    commit_sha = Column('prref_commit_sha', VARCHAR(64), nullable=False,
                        doc="Commit the ref pointed at (the peeled commit for annotated tags)")
    first_seen_at = Column('prref_first_seen_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                           doc="Timestamp of the fetch that first saw the ref")
    updated_at = Column('prref_updated_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp of the fetch that last saw the ref move")



class ProjectBuildTriggerType(str, enum.Enum):
    """
        Enum-like class to represent the trigger types for project builds.
    """
    MANUAL = 'manual'
    WEBHOOK = 'webhook'
    SCHEDULE = 'schedule'
    WATCH = 'watch'
    API = 'api'


class ProjectJobStatus(str, enum.Enum):
    """
        Enum-like class to represent the status of project jobs.
    """
    PENDING = 'pending'
    QUEUED = 'queued'
    RUNNING = 'running'
    SUCCEEDED = 'succeeded'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


class ProjectBuildSpec(PychestrateModelBase, SerializableModel):
    """
        A data model for storing build specifications.
        Build specifications define how to build artifacts from repository source code.
    """
    __tablename__ = 'project_build_specs'

    __table_args__ = (
        UniqueConstraint('proj_id', 'pbspec_name', name='uq_project_build_spec_name'),
        Index('ix_project_build_specs_project_name', 'proj_id', 'pbspec_name'),
    )

    id = Column('pbspec_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    project_id = Column('proj_id', BigInteger, ForeignKey('projects.proj_id'), nullable=False, index=True,
                        doc="Reference to the project")
    repository_id = Column('prepo_id', BigInteger, ForeignKey('project_repositories.prepo_id'), nullable=False, index=True,
                           doc="Reference to the repository")
    name = Column('pbspec_name', VARCHAR(128), nullable=False,
                  doc="Name of the build specification (unique within project)")
    branch = Column('pbspec_branch', VARCHAR(128), default='main', nullable=False,
                    doc="Default branch to build from")
    steps_json = Column('pbspec_steps_json', JSON, default=[], nullable=False,
                        doc="JSON-encoded list of build steps")
    environment_json = Column('pbspec_environment_json', JSON, default={}, nullable=False,
                              doc="JSON-encoded environment variables")
    timeout_minutes = Column('pbspec_timeout_minutes', Integer, default=60, nullable=False,
                             doc="Timeout for the build in minutes")
    description = Column('pbspec_description', VARCHAR(512), nullable=True,
                         doc="Human-readable description of the build specification")
    version = Column('pbspec_version', Integer, default=1, nullable=False,
                     doc="Version number, incremented on each update")
    created_at = Column('pbspec_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the specification was created")
    updated_at = Column('pbspec_updated_at', UtcDateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False,
                        doc="Timestamp when the specification was last updated")

    project = relationship('Project', back_populates='build_specs', lazy='selectin')
    repository = relationship('ProjectRepository', back_populates='build_specs', lazy='selectin')
    builds = relationship('ProjectBuild', back_populates='spec', lazy='selectin')


class ProjectBuild(PychestrateModelBase, SerializableModel):
    """
        A data model for storing build execution records.
        Each build represents an execution instance of a build specification.
    """
    __tablename__ = 'project_builds'

    __table_args__ = (
        Index('ix_project_builds_project_status', 'proj_id', 'pbuild_status'),
        Index('ix_project_builds_spec_status', 'pbspec_id', 'pbuild_status'),
    )

    id = Column('pbuild_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    project_id = Column('proj_id', BigInteger, ForeignKey('projects.proj_id'), nullable=False, index=True,
                        doc="Reference to the project")
    spec_id = Column('pbspec_id', BigInteger, ForeignKey('project_build_specs.pbspec_id'), nullable=False, index=True,
                     doc="Reference to the build specification")
    spec_version = Column('pbuild_spec_version', Integer, nullable=False,
                          doc="Version of the specification used for this build")
    branch = Column('pbuild_branch', VARCHAR(128), nullable=False,
                    doc="Branch that was built")
    commit_sha = Column('pbuild_commit_sha', VARCHAR(64), nullable=False,
                        doc="SHA of the commit that was built")
    commit_message = Column('pbuild_commit_message', VARCHAR(512), nullable=True,
                            doc="Message of the commit that was built")
    status = Column('pbuild_status', VARCHAR(32), default='pending', nullable=False,
                    doc="Status of the build (pending, queued, running, succeeded, failed, cancelled)")
    trigger_type = Column('pbuild_trigger_type', VARCHAR(32), nullable=False,
                          doc="Type of trigger that started the build")
    triggered_by_id = Column('pbuild_triggered_by_id', UUIDType, ForeignKey('user.user_id'), nullable=False, index=True,
                             doc="Reference to the user who triggered the build")
    parameters_json = Column('pbuild_parameters_json', JSON, default={}, nullable=False,
                             doc="JSON-encoded parameters for the build")
    started_at = Column('pbuild_started_at', UtcDateTime(timezone=True), nullable=True,
                        doc="Timestamp when the build started")
    completed_at = Column('pbuild_completed_at', UtcDateTime(timezone=True), nullable=True,
                          doc="Timestamp when the build completed")
    duration_seconds = Column('pbuild_duration_seconds', Integer, nullable=True,
                              doc="Duration of the build in seconds")
    logs_path = Column('pbuild_logs_path', VARCHAR(512), nullable=True,
                       doc="Path to the build logs")
    created_at = Column('pbuild_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the build record was created")

    spec = relationship('ProjectBuildSpec', back_populates='builds', lazy='selectin')
    artifacts = relationship('ProjectBuildArtifact', back_populates='build', cascade='all, delete-orphan', lazy='selectin')


class ProjectBuildArtifact(PychestrateModelBase, SerializableModel):
    """
        A data model for storing build artifacts.
        Artifacts are files produced by a build.
    """
    __tablename__ = 'project_build_artifacts'

    id = Column('pbartifact_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    build_id = Column('pbuild_id', BigInteger, ForeignKey('project_builds.pbuild_id'), nullable=False, index=True,
                      doc="Reference to the build")
    name = Column('pbartifact_name', VARCHAR(256), nullable=False,
                  doc="Name of the artifact")
    path = Column('pbartifact_path', VARCHAR(512), nullable=False,
                  doc="Storage path of the artifact")
    size_bytes = Column('pbartifact_size_bytes', BigInteger, nullable=False,
                        doc="Size of the artifact in bytes")
    checksum = Column('pbartifact_checksum', VARCHAR(128), nullable=False,
                      doc="Checksum of the artifact")
    checksum_algorithm = Column('pbartifact_checksum_algorithm', VARCHAR(16), default='sha256', nullable=False,
                                doc="Algorithm used for the checksum")
    created_at = Column('pbartifact_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the artifact was created")

    build = relationship('ProjectBuild', back_populates='artifacts', lazy='selectin')



class ProjectInfraProvider(str, enum.Enum):
    """
        Enum-like class to represent the infrastructure providers.
    """
    LOCAL = 'local'
    DOCKER = 'docker'
    KUBERNETES = 'kubernetes'
    AWS = 'aws'
    AZURE = 'azure'
    GCP = 'gcp'


class ProjectInfraAction(str, enum.Enum):
    """
        Enum-like class to represent the infrastructure job actions.
    """
    PROVISION = 'provision'
    UPDATE = 'update'
    DESTROY = 'destroy'


class ProjectInfraState(str, enum.Enum):
    """
        Enum-like class to represent the infrastructure lifecycle state.
    """
    PENDING = 'pending'
    PROVISIONING = 'provisioning'
    RUNNING = 'running'
    UPDATING = 'updating'
    DESTROYING = 'destroying'
    DESTROYED = 'destroyed'
    FAILED = 'failed'


class ProjectInfraSpec(PychestrateModelBase, SerializableModel):
    """
        A data model for storing infrastructure specifications.
        Infrastructure specifications define infrastructure to provision.
    """
    __tablename__ = 'project_infra_specs'

    __table_args__ = (
        UniqueConstraint('proj_id', 'pispec_name', name='uq_project_infra_spec_name'),
        Index('ix_project_infra_specs_project_name', 'proj_id', 'pispec_name'),
    )

    id = Column('pispec_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    project_id = Column('proj_id', BigInteger, ForeignKey('projects.proj_id'), nullable=False, index=True,
                        doc="Reference to the project")
    name = Column('pispec_name', VARCHAR(128), nullable=False,
                  doc="Name of the infrastructure specification (unique within project)")
    provider = Column('pispec_provider', VARCHAR(32), nullable=False,
                      doc="Infrastructure provider (local, docker, kubernetes, aws, azure, gcp)")
    resources_json = Column('pispec_resources_json', JSON, default=[], nullable=False,
                            doc="JSON-encoded list of resource definitions")
    variables_json = Column('pispec_variables_json', JSON, default={}, nullable=False,
                            doc="JSON-encoded variables for the specification")
    timeout_minutes = Column('pispec_timeout_minutes', Integer, default=30, nullable=False,
                             doc="Timeout for infrastructure operations in minutes")
    description = Column('pispec_description', VARCHAR(512), nullable=True,
                         doc="Human-readable description of the infrastructure specification")
    version = Column('pispec_version', Integer, default=1, nullable=False,
                     doc="Version number, incremented on each update")
    created_at = Column('pispec_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the specification was created")
    updated_at = Column('pispec_updated_at', UtcDateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False,
                        doc="Timestamp when the specification was last updated")

    project = relationship('Project', back_populates='infra_specs', lazy='selectin')
    jobs = relationship('ProjectInfraJob', back_populates='spec', lazy='selectin')


class ProjectInfraJob(PychestrateModelBase, SerializableModel):
    """
        A data model for storing infrastructure job execution records.
        Each job represents an execution instance of an infrastructure specification.
    """
    __tablename__ = 'project_infra_jobs'

    __table_args__ = (
        Index('ix_project_infra_jobs_project_state', 'proj_id', 'pijob_state'),
        Index('ix_project_infra_jobs_spec_status', 'pispec_id', 'pijob_status'),
    )

    id = Column('pijob_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    project_id = Column('proj_id', BigInteger, ForeignKey('projects.proj_id'), nullable=False, index=True,
                        doc="Reference to the project")
    spec_id = Column('pispec_id', BigInteger, ForeignKey('project_infra_specs.pispec_id'), nullable=False, index=True,
                     doc="Reference to the infrastructure specification")
    spec_version = Column('pijob_spec_version', Integer, nullable=False,
                          doc="Version of the specification used for this job")
    action = Column('pijob_action', VARCHAR(32), nullable=False,
                    doc="Action to perform (provision, update, destroy)")
    state = Column('pijob_state', VARCHAR(32), default='pending', nullable=False,
                   doc="Infrastructure lifecycle state")
    status = Column('pijob_status', VARCHAR(32), default='pending', nullable=False,
                    doc="Job execution status (pending, queued, running, succeeded, failed, cancelled)")
    triggered_by_id = Column('pijob_triggered_by_id', UUIDType, ForeignKey('user.user_id'), nullable=False, index=True,
                             doc="Reference to the user who triggered the job")
    variables_json = Column('pijob_variables_json', JSON, default={}, nullable=False,
                            doc="JSON-encoded variables for the job")
    provisioned_resources_json = Column('pijob_provisioned_resources_json', JSON, default=[], nullable=False,
                                        doc="JSON-encoded list of provisioned resources")
    connection_details_json = Column('pijob_connection_details_json', JSON, default={}, nullable=False,
                                     doc="JSON-encoded connection details for provisioned infrastructure")
    started_at = Column('pijob_started_at', UtcDateTime(timezone=True), nullable=True,
                        doc="Timestamp when the job started")
    completed_at = Column('pijob_completed_at', UtcDateTime(timezone=True), nullable=True,
                          doc="Timestamp when the job completed")
    duration_seconds = Column('pijob_duration_seconds', Integer, nullable=True,
                              doc="Duration of the job in seconds")
    logs_path = Column('pijob_logs_path', VARCHAR(512), nullable=True,
                       doc="Path to the job logs")
    created_at = Column('pijob_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the job record was created")

    spec = relationship('ProjectInfraSpec', back_populates='jobs', lazy='selectin')



class ProjectTestFramework(str, enum.Enum):
    """
        Enum-like class to represent the test frameworks.
    """
    PYTEST = 'pytest'
    UNITTEST = 'unittest'
    TESTBASE = 'testbase'
    CUSTOM = 'custom'


class ProjectTestResultFormat(str, enum.Enum):
    """
        Enum-like class to represent the test result formats.
    """
    JUNIT_XML = 'junit_xml'
    TAP = 'tap'
    JSON = 'json'


class ProjectTestSpec(PychestrateModelBase, SerializableModel):
    """
        A data model for storing test specifications.
        Test specifications define tests to execute against builds and infrastructure.
    """
    __tablename__ = 'project_test_specs'

    __table_args__ = (
        UniqueConstraint('proj_id', 'ptspec_name', name='uq_project_test_spec_name'),
        Index('ix_project_test_specs_project_name', 'proj_id', 'ptspec_name'),
    )

    id = Column('ptspec_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    project_id = Column('proj_id', BigInteger, ForeignKey('projects.proj_id'), nullable=False, index=True,
                        doc="Reference to the project")
    name = Column('ptspec_name', VARCHAR(128), nullable=False,
                  doc="Name of the test specification (unique within project)")
    framework = Column('ptspec_framework', VARCHAR(32), nullable=False,
                       doc="Test framework (pytest, unittest, testbase, custom)")
    test_command = Column('ptspec_test_command', VARCHAR(1024), nullable=False,
                          doc="Command to execute tests")
    test_selection = Column('ptspec_test_selection', VARCHAR(512), nullable=True,
                            doc="Test filter/pattern for selecting tests")
    build_ref = Column('ptspec_build_ref', BigInteger, ForeignKey('project_build_specs.pbspec_id'), nullable=True,
                       doc="Reference to build specification for artifacts")
    infra_ref = Column('ptspec_infra_ref', BigInteger, ForeignKey('project_infra_specs.pispec_id'), nullable=True,
                       doc="Reference to infrastructure specification for test environment")
    environment_json = Column('ptspec_environment_json', JSON, default={}, nullable=False,
                              doc="JSON-encoded environment variables")
    timeout_minutes = Column('ptspec_timeout_minutes', Integer, default=60, nullable=False,
                             doc="Timeout for test execution in minutes")
    result_format = Column('ptspec_result_format', VARCHAR(32), default='junit_xml', nullable=False,
                           doc="Format of test results (junit_xml, tap, json)")
    description = Column('ptspec_description', VARCHAR(512), nullable=True,
                         doc="Human-readable description of the test specification")
    version = Column('ptspec_version', Integer, default=1, nullable=False,
                     doc="Version number, incremented on each update")
    created_at = Column('ptspec_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the specification was created")
    updated_at = Column('ptspec_updated_at', UtcDateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False,
                        doc="Timestamp when the specification was last updated")

    project = relationship('Project', back_populates='test_specs', lazy='selectin')
    jobs = relationship('ProjectTestJob', back_populates='spec', lazy='selectin')


class ProjectTestJob(PychestrateModelBase, SerializableModel):
    """
        A data model for storing test job execution records.
        Each job represents an execution instance of a test specification.
    """
    __tablename__ = 'project_test_jobs'

    __table_args__ = (
        Index('ix_project_test_jobs_project_status', 'proj_id', 'ptjob_status'),
        Index('ix_project_test_jobs_spec_status', 'ptspec_id', 'ptjob_status'),
    )

    id = Column('ptjob_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    project_id = Column('proj_id', BigInteger, ForeignKey('projects.proj_id'), nullable=False, index=True,
                        doc="Reference to the project")
    spec_id = Column('ptspec_id', BigInteger, ForeignKey('project_test_specs.ptspec_id'), nullable=False, index=True,
                     doc="Reference to the test specification")
    spec_version = Column('ptjob_spec_version', Integer, nullable=False,
                          doc="Version of the specification used for this job")
    build_id = Column('ptjob_build_id', BigInteger, ForeignKey('project_builds.pbuild_id'), nullable=True,
                      doc="Reference to the build being tested")
    infra_job_id = Column('ptjob_infra_job_id', BigInteger, ForeignKey('project_infra_jobs.pijob_id'), nullable=True,
                          doc="Reference to the infrastructure job providing test environment")
    status = Column('ptjob_status', VARCHAR(32), default='pending', nullable=False,
                    doc="Job execution status (pending, queued, running, succeeded, failed, cancelled)")
    triggered_by_id = Column('ptjob_triggered_by_id', UUIDType, ForeignKey('user.user_id'), nullable=False, index=True,
                             doc="Reference to the user who triggered the job")
    parameters_json = Column('ptjob_parameters_json', JSON, default={}, nullable=False,
                             doc="JSON-encoded parameters for the job")
    result_summary_json = Column('ptjob_result_summary_json', JSON, nullable=True,
                                 doc="JSON-encoded test result summary (total, passed, failed, skipped, errors)")
    started_at = Column('ptjob_started_at', UtcDateTime(timezone=True), nullable=True,
                        doc="Timestamp when the job started")
    completed_at = Column('ptjob_completed_at', UtcDateTime(timezone=True), nullable=True,
                          doc="Timestamp when the job completed")
    duration_seconds = Column('ptjob_duration_seconds', Integer, nullable=True,
                              doc="Duration of the job in seconds")
    logs_path = Column('ptjob_logs_path', VARCHAR(512), nullable=True,
                       doc="Path to the job logs")
    results_path = Column('ptjob_results_path', VARCHAR(512), nullable=True,
                          doc="Path to the test results file")
    created_at = Column('ptjob_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the job record was created")

    spec = relationship('ProjectTestSpec', back_populates='jobs', lazy='selectin')
    results = relationship('ProjectTestResult', back_populates='job', cascade='all, delete-orphan', lazy='selectin')


class ProjectTestResult(PychestrateModelBase, SerializableModel):
    """
        A data model for storing individual test case results.
    """
    __tablename__ = 'project_test_results'

    id = Column('ptresult_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    job_id = Column('ptjob_id', BigInteger, ForeignKey('project_test_jobs.ptjob_id'), nullable=False, index=True,
                    doc="Reference to the test job")
    name = Column('ptresult_name', VARCHAR(512), nullable=False,
                  doc="Name of the test case")
    classname = Column('ptresult_classname', VARCHAR(512), nullable=True,
                       doc="Class name of the test case")
    status = Column('ptresult_status', VARCHAR(32), nullable=False,
                    doc="Status of the test case (passed, failed, skipped, error)")
    duration_seconds = Column('ptresult_duration_seconds', Float, nullable=True,
                              doc="Duration of the test case in seconds")
    failure_message = Column('ptresult_failure_message', Text, nullable=True,
                             doc="Failure message if the test failed")
    failure_trace = Column('ptresult_failure_trace', Text, nullable=True,
                           doc="Stack trace if the test failed")

    job = relationship('ProjectTestJob', back_populates='results', lazy='selectin')



class ProjectReleaseStatus(str, enum.Enum):
    """
        Enum-like class to represent the status of a release.
    """
    DRAFT = 'draft'
    PENDING_APPROVAL = 'pending_approval'
    APPROVED = 'approved'
    PUBLISHED = 'published'
    DEPRECATED = 'deprecated'
    RECALLED = 'recalled'


class ProjectPipelineStageType(str, enum.Enum):
    """
        Enum-like class to represent the types of pipeline stages.
    """
    CHECKOUT = 'checkout'
    BUILD = 'build'
    TEST = 'test'
    PACKAGE = 'package'
    SIGN = 'sign'
    PUBLISH = 'publish'
    NOTIFY = 'notify'
    APPROVAL = 'approval'


class ProjectPipelineTriggerType(str, enum.Enum):
    """
        Enum-like class to represent the trigger types for release pipelines.
    """
    MANUAL = 'manual'
    TAG_PUSH = 'tag_push'
    BRANCH_MERGE = 'branch_merge'
    SCHEDULE = 'schedule'
    API = 'api'
    WATCH = 'watch'


class ProjectArtifactType(str, enum.Enum):
    """
        Enum-like class to represent the types of release artifacts.
    """
    BINARY = 'binary'
    ARCHIVE = 'archive'
    CONTAINER_IMAGE = 'container_image'
    PACKAGE = 'package'
    DOCUMENTATION = 'documentation'
    CUSTOM = 'custom'


class ProjectReleasePipeline(PychestrateModelBase, SerializableModel):
    """
        A data model for storing release pipeline definitions.
        Release pipelines define the sequence of stages to produce a release.
    """
    __tablename__ = 'project_release_pipelines'

    __table_args__ = (
        UniqueConstraint('proj_id', 'prpipe_name', name='uq_project_release_pipeline_name'),
        Index('ix_project_release_pipelines_project_name', 'proj_id', 'prpipe_name'),
    )

    id = Column('prpipe_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    project_id = Column('proj_id', BigInteger, ForeignKey('projects.proj_id'), nullable=False, index=True,
                        doc="Reference to the project")
    name = Column('prpipe_name', VARCHAR(128), nullable=False,
                  doc="Name of the release pipeline (unique within project)")
    stages_json = Column('prpipe_stages_json', JSON, default=[], nullable=False,
                         doc="JSON-encoded list of pipeline stages")
    triggers_json = Column('prpipe_triggers_json', JSON, default=[], nullable=False,
                           doc="JSON-encoded list of trigger types")
    variables_json = Column('prpipe_variables_json', JSON, default={}, nullable=False,
                            doc="JSON-encoded variables for the pipeline")
    description = Column('prpipe_description', VARCHAR(512), nullable=True,
                         doc="Human-readable description of the pipeline")
    version = Column('prpipe_version', Integer, default=1, nullable=False,
                     doc="Version number, incremented on each update")
    created_at = Column('prpipe_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the pipeline was created")
    updated_at = Column('prpipe_updated_at', UtcDateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False,
                        doc="Timestamp when the pipeline was last updated")

    project = relationship('Project', back_populates='release_pipelines', lazy='selectin')
    runs = relationship('ProjectPipelineRun', back_populates='pipeline', lazy='selectin')
    schedules = relationship('ProjectReleaseSchedule', back_populates='pipeline', lazy='selectin')


class ProjectPipelineRun(PychestrateModelBase, SerializableModel):
    """
        A data model for storing pipeline run execution records.
    """
    __tablename__ = 'project_pipeline_runs'

    __table_args__ = (
        Index('ix_project_pipeline_runs_pipeline_status', 'prpipe_id', 'prrun_status'),
    )

    id = Column('prrun_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    pipeline_id = Column('prpipe_id', BigInteger, ForeignKey('project_release_pipelines.prpipe_id'), nullable=False, index=True,
                         doc="Reference to the release pipeline")
    pipeline_version = Column('prrun_pipeline_version', Integer, nullable=False,
                              doc="Version of the pipeline used for this run")
    status = Column('prrun_status', VARCHAR(32), default='pending', nullable=False,
                    doc="Status of the pipeline run")
    current_stage = Column('prrun_current_stage', VARCHAR(128), nullable=True,
                           doc="Name of the currently executing stage")
    trigger_type = Column('prrun_trigger_type', VARCHAR(32), nullable=False,
                          doc="Type of trigger that started the run")
    triggered_by_id = Column('prrun_triggered_by_id', UUIDType, ForeignKey('user.user_id'), nullable=False, index=True,
                             doc="Reference to the user who triggered the run")
    variables_json = Column('prrun_variables_json', JSON, default={}, nullable=False,
                            doc="JSON-encoded variables for the run")
    release_id = Column('prrun_release_id', BigInteger, ForeignKey('project_releases.prelease_id'), nullable=True,
                        doc="Reference to the release created by this run")
    started_at = Column('prrun_started_at', UtcDateTime(timezone=True), nullable=True,
                        doc="Timestamp when the run started")
    completed_at = Column('prrun_completed_at', UtcDateTime(timezone=True), nullable=True,
                          doc="Timestamp when the run completed")
    created_at = Column('prrun_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the run record was created")

    pipeline = relationship('ProjectReleasePipeline', back_populates='runs', lazy='selectin')
    stage_runs = relationship('ProjectStageRun', back_populates='pipeline_run', cascade='all, delete-orphan', lazy='selectin')


class ProjectStageRun(PychestrateModelBase, SerializableModel):
    """
        A data model for storing individual stage run records within a pipeline run.
    """
    __tablename__ = 'project_stage_runs'

    id = Column('pstagerun_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    pipeline_run_id = Column('prrun_id', BigInteger, ForeignKey('project_pipeline_runs.prrun_id'), nullable=False, index=True,
                             doc="Reference to the pipeline run")
    stage_name = Column('pstagerun_stage_name', VARCHAR(128), nullable=False,
                        doc="Name of the stage")
    stage_type = Column('pstagerun_stage_type', VARCHAR(32), nullable=False,
                        doc="Type of the stage")
    status = Column('pstagerun_status', VARCHAR(32), default='pending', nullable=False,
                    doc="Status of the stage run")
    requires_approval = Column('pstagerun_requires_approval', Boolean, default=False, nullable=False,
                               doc="Flag indicating if the stage requires manual approval")
    approved_by_id = Column('pstagerun_approved_by_id', UUIDType, ForeignKey('user.user_id'), nullable=True,
                            doc="Reference to the user who approved the stage")
    approved_at = Column('pstagerun_approved_at', UtcDateTime(timezone=True), nullable=True,
                         doc="Timestamp when the stage was approved")
    started_at = Column('pstagerun_started_at', UtcDateTime(timezone=True), nullable=True,
                        doc="Timestamp when the stage started")
    completed_at = Column('pstagerun_completed_at', UtcDateTime(timezone=True), nullable=True,
                          doc="Timestamp when the stage completed")
    logs_path = Column('pstagerun_logs_path', VARCHAR(512), nullable=True,
                       doc="Path to the stage logs")
    output_json = Column('pstagerun_output_json', JSON, default={}, nullable=False,
                         doc="JSON-encoded output from the stage")

    pipeline_run = relationship('ProjectPipelineRun', back_populates='stage_runs', lazy='selectin')


class ProjectRelease(PychestrateModelBase, SerializableModel):
    """
        A data model for storing release records.
        Releases are versioned collections of artifacts representing deployable units.
    """
    __tablename__ = 'project_releases'

    __table_args__ = (
        UniqueConstraint('proj_id', 'prelease_version', name='uq_project_release_version'),
        Index('ix_project_releases_project_version', 'proj_id', 'prelease_version'),
        Index('ix_project_releases_project_status', 'proj_id', 'prelease_status'),
    )

    id = Column('prelease_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    project_id = Column('proj_id', BigInteger, ForeignKey('projects.proj_id'), nullable=False, index=True,
                        doc="Reference to the project")
    version = Column('prelease_version', VARCHAR(64), nullable=False,
                     doc="Version string (semantic versioning or custom pattern)")
    name = Column('prelease_name', VARCHAR(256), nullable=False,
                  doc="Human-readable name for the release")
    description = Column('prelease_description', Text, nullable=True,
                         doc="Description of the release")
    status = Column('prelease_status', VARCHAR(32), default='draft', nullable=False,
                    doc="Status of the release (draft, pending_approval, approved, published, deprecated, recalled)")
    metadata_json = Column('prelease_metadata_json', JSON, default={}, nullable=False,
                           doc="JSON-encoded metadata for the release")
    pipeline_run_id = Column('prelease_pipeline_run_id', BigInteger, ForeignKey('project_pipeline_runs.prrun_id'), nullable=True,
                             doc="Reference to the pipeline run that created this release")
    schedule_id = Column('prelease_schedule_id', BigInteger, ForeignKey('project_release_schedules.prsched_id'), nullable=True,
                         doc="Reference to the schedule that created this release")
    created_at = Column('prelease_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the release was created")
    updated_at = Column('prelease_updated_at', UtcDateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False,
                        doc="Timestamp when the release was last updated")
    published_at = Column('prelease_published_at', UtcDateTime(timezone=True), nullable=True,
                          doc="Timestamp when the release was published")
    published_by_id = Column('prelease_published_by_id', UUIDType, ForeignKey('user.user_id'), nullable=True,
                             doc="Reference to the user who published the release")

    project = relationship('Project', back_populates='releases', lazy='selectin')
    artifacts = relationship('ProjectReleaseArtifact', back_populates='release', cascade='all, delete-orphan', lazy='selectin')
    branches = relationship('ProjectReleaseBranch', back_populates='release', cascade='all, delete-orphan', lazy='selectin')
    events = relationship('ProjectReleaseEvent', back_populates='release', cascade='all, delete-orphan', lazy='selectin')
    merge_events = relationship('ProjectMergeEvent', back_populates='release', cascade='all, delete-orphan', lazy='selectin')
    pull_events = relationship('ProjectPullEvent', back_populates='release', cascade='all, delete-orphan', lazy='selectin')


class ProjectReleaseArtifact(PychestrateModelBase, SerializableModel):
    """
        A data model for storing release artifacts.
    """
    __tablename__ = 'project_release_artifacts'

    id = Column('prartifact_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    release_id = Column('prelease_id', BigInteger, ForeignKey('project_releases.prelease_id'), nullable=False, index=True,
                        doc="Reference to the release")
    name = Column('prartifact_name', VARCHAR(256), nullable=False,
                  doc="Name of the artifact")
    artifact_type = Column('prartifact_type', VARCHAR(32), nullable=False,
                           doc="Type of artifact (binary, archive, container_image, package, documentation, custom)")
    size_bytes = Column('prartifact_size_bytes', BigInteger, nullable=False,
                        doc="Size of the artifact in bytes")
    checksum = Column('prartifact_checksum', VARCHAR(128), nullable=False,
                      doc="Checksum of the artifact")
    checksum_algorithm = Column('prartifact_checksum_algorithm', VARCHAR(16), default='sha256', nullable=False,
                                doc="Algorithm used for the checksum")
    storage_path = Column('prartifact_storage_path', VARCHAR(512), nullable=False,
                          doc="Storage path of the artifact")
    signature = Column('prartifact_signature', Text, nullable=True,
                       doc="Digital signature of the artifact")
    created_at = Column('prartifact_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the artifact was created")

    release = relationship('ProjectRelease', back_populates='artifacts', lazy='selectin')


class ProjectReleaseChannel(PychestrateModelBase, SerializableModel):
    """
        A data model for storing release channels.
        Channels are distribution tracks for releases (dev, staging, production).
    """
    __tablename__ = 'project_release_channels'

    __table_args__ = (
        UniqueConstraint('proj_id', 'prchan_name', name='uq_project_release_channel_name'),
        Index('ix_project_release_channels_project_name', 'proj_id', 'prchan_name'),
    )

    id = Column('prchan_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    project_id = Column('proj_id', BigInteger, ForeignKey('projects.proj_id'), nullable=False, index=True,
                        doc="Reference to the project")
    name = Column('prchan_name', VARCHAR(64), nullable=False,
                  doc="Name of the channel (unique within project)")
    description = Column('prchan_description', VARCHAR(512), nullable=True,
                         doc="Human-readable description of the channel")
    current_release_id = Column('prchan_current_release_id', BigInteger, ForeignKey('project_releases.prelease_id'), nullable=True,
                                doc="Reference to the current release on this channel")
    requires_approval = Column('prchan_requires_approval', Boolean, default=False, nullable=False,
                               doc="Flag indicating if publishing to this channel requires approval")
    created_at = Column('prchan_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the channel was created")
    updated_at = Column('prchan_updated_at', UtcDateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False,
                        doc="Timestamp when the channel was last updated")

    project = relationship('Project', back_populates='release_channels', lazy='selectin')
    history = relationship('ProjectChannelHistory', back_populates='channel', cascade='all, delete-orphan', lazy='selectin')


class ProjectChannelHistory(PychestrateModelBase, SerializableModel):
    """
        A data model for tracking release history on channels.
    """
    __tablename__ = 'project_channel_history'

    id = Column('pchanhist_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    channel_id = Column('prchan_id', BigInteger, ForeignKey('project_release_channels.prchan_id'), nullable=False, index=True,
                        doc="Reference to the channel")
    release_id = Column('prelease_id', BigInteger, ForeignKey('project_releases.prelease_id'), nullable=False, index=True,
                        doc="Reference to the release")
    published_at = Column('pchanhist_published_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                          doc="Timestamp when the release was published to the channel")
    published_by_id = Column('pchanhist_published_by_id', UUIDType, ForeignKey('user.user_id'), nullable=False,
                             doc="Reference to the user who published the release")

    channel = relationship('ProjectReleaseChannel', back_populates='history', lazy='selectin')


class ProjectReleaseSchedule(PychestrateModelBase, SerializableModel):
    """
        A data model for storing release schedules.
        Schedules define automated release triggers based on cron expressions.
    """
    __tablename__ = 'project_release_schedules'

    __table_args__ = (
        UniqueConstraint('proj_id', 'prsched_name', name='uq_project_release_schedule_name'),
        Index('ix_project_release_schedules_project_name', 'proj_id', 'prsched_name'),
        Index('ix_project_release_schedules_next_run', 'prsched_enabled', 'prsched_next_run_time'),
    )

    id = Column('prsched_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    project_id = Column('proj_id', BigInteger, ForeignKey('projects.proj_id'), nullable=False, index=True,
                        doc="Reference to the project")
    name = Column('prsched_name', VARCHAR(128), nullable=False,
                  doc="Name of the schedule (unique within project)")
    cron_expression = Column('prsched_cron_expression', VARCHAR(128), nullable=False,
                             doc="Cron expression for the schedule")
    pipeline_id = Column('prsched_pipeline_id', BigInteger, ForeignKey('project_release_pipelines.prpipe_id'), nullable=False,
                         doc="Reference to the release pipeline to trigger")
    variables_json = Column('prsched_variables_json', JSON, default={}, nullable=False,
                            doc="JSON-encoded variables to pass to the pipeline")
    enabled = Column('prsched_enabled', Boolean, default=True, nullable=False,
                     doc="Flag indicating if the schedule is enabled")
    description = Column('prsched_description', VARCHAR(512), nullable=True,
                         doc="Human-readable description of the schedule")
    last_run_time = Column('prsched_last_run_time', UtcDateTime(timezone=True), nullable=True,
                           doc="Timestamp of the last scheduled run")
    next_run_time = Column('prsched_next_run_time', UtcDateTime(timezone=True), nullable=True,
                           doc="Timestamp of the next scheduled run")
    run_count = Column('prsched_run_count', Integer, default=0, nullable=False,
                       doc="Number of times the schedule has been triggered")
    created_at = Column('prsched_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the schedule was created")
    updated_at = Column('prsched_updated_at', UtcDateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False,
                        doc="Timestamp when the schedule was last updated")

    project = relationship('Project')
    pipeline = relationship('ProjectReleasePipeline', back_populates='schedules', lazy='selectin')



class ProjectCalendarEventType(str, enum.Enum):
    """
        Enum-like class to represent the types of calendar events.
    """
    RELEASE = 'release'
    PHASE = 'phase'
    MERGE = 'merge'
    PULL = 'pull'


class ProjectPhaseStatus(str, enum.Enum):
    """
        Enum-like class to represent the status of a phase event.
    """
    PLANNED = 'planned'
    IN_PROGRESS = 'in_progress'
    COMPLETED = 'completed'


class ProjectBranchEventStatus(str, enum.Enum):
    """
        Enum-like class to represent the status of merge/pull events.
    """
    SCHEDULED = 'scheduled'
    IN_PROGRESS = 'in_progress'
    COMPLETED = 'completed'
    FAILED = 'failed'


class ProjectCalendarEvent(PychestrateModelBase, SerializableModel):
    """
        A base data model for calendar events.
        This provides a unified view of all calendar events for a project.
    """
    __tablename__ = 'project_calendar_events'

    __table_args__ = (
        Index('ix_project_calendar_events_project_time', 'proj_id', 'pcalevent_start_time', 'pcalevent_end_time'),
        Index('ix_project_calendar_events_type', 'pcalevent_event_type'),
    )

    id = Column('pcalevent_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    project_id = Column('proj_id', BigInteger, ForeignKey('projects.proj_id'), nullable=False, index=True,
                        doc="Reference to the project")
    event_type = Column('pcalevent_event_type', VARCHAR(32), nullable=False,
                        doc="Type of calendar event (release, phase, merge, pull)")
    name = Column('pcalevent_name', VARCHAR(256), nullable=False,
                  doc="Name of the event")
    description = Column('pcalevent_description', Text, nullable=True,
                         doc="Description of the event")
    start_time = Column('pcalevent_start_time', UtcDateTime(timezone=True), nullable=False,
                        doc="Start time of the event")
    end_time = Column('pcalevent_end_time', UtcDateTime(timezone=True), nullable=False,
                      doc="End time of the event")
    created_at = Column('pcalevent_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the event was created")
    updated_at = Column('pcalevent_updated_at', UtcDateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False,
                        doc="Timestamp when the event was last updated")


class ProjectReleaseEvent(PychestrateModelBase, SerializableModel):
    """
        A data model for storing release calendar events.
        Release events represent planned release windows on the calendar.
    """
    __tablename__ = 'project_release_events'

    __table_args__ = (
        Index('ix_project_release_events_project_time', 'proj_id', 'prelevent_start_time', 'prelevent_end_time'),
        Index('ix_project_release_events_release', 'prelease_id'),
    )

    id = Column('prelevent_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    project_id = Column('proj_id', BigInteger, ForeignKey('projects.proj_id'), nullable=False, index=True,
                        doc="Reference to the project")
    release_id = Column('prelease_id', BigInteger, ForeignKey('project_releases.prelease_id'), nullable=False, index=True,
                        doc="Reference to the release")
    name = Column('prelevent_name', VARCHAR(256), nullable=False,
                  doc="Name of the release event")
    description = Column('prelevent_description', Text, nullable=True,
                         doc="Description of the release event")
    start_time = Column('prelevent_start_time', UtcDateTime(timezone=True), nullable=False,
                        doc="Start time of the release event")
    end_time = Column('prelevent_end_time', UtcDateTime(timezone=True), nullable=False,
                      doc="End time of the release event")
    created_at = Column('prelevent_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the event was created")
    updated_at = Column('prelevent_updated_at', UtcDateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False,
                        doc="Timestamp when the event was last updated")

    release = relationship('ProjectRelease', back_populates='events', lazy='selectin')
    phases = relationship('ProjectPhaseEvent', back_populates='release_event', cascade='all, delete-orphan', lazy='selectin')


class ProjectPhaseEvent(PychestrateModelBase, SerializableModel):
    """
        A data model for storing phase events within a release event.
        Phases divide a release into distinct stages.
    """
    __tablename__ = 'project_phase_events'

    __table_args__ = (
        Index('ix_project_phase_events_release_order', 'prelevent_id', 'pphase_order'),
    )

    id = Column('pphase_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    release_event_id = Column('prelevent_id', BigInteger, ForeignKey('project_release_events.prelevent_id'), nullable=False, index=True,
                              doc="Reference to the release event")
    name = Column('pphase_name', VARCHAR(256), nullable=False,
                  doc="Name of the phase")
    description = Column('pphase_description', Text, nullable=True,
                         doc="Description of the phase")
    start_time = Column('pphase_start_time', UtcDateTime(timezone=True), nullable=False,
                        doc="Start time of the phase")
    end_time = Column('pphase_end_time', UtcDateTime(timezone=True), nullable=False,
                      doc="End time of the phase")
    order = Column('pphase_order', Integer, nullable=False,
                   doc="Order of the phase within the release event")
    status = Column('pphase_status', VARCHAR(32), default='planned', nullable=False,
                    doc="Status of the phase (planned, in_progress, completed)")
    created_at = Column('pphase_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the phase was created")
    updated_at = Column('pphase_updated_at', UtcDateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False,
                        doc="Timestamp when the phase was last updated")

    release_event = relationship('ProjectReleaseEvent', back_populates='phases', lazy='selectin')


class ProjectReleaseBranch(PychestrateModelBase, SerializableModel):
    """
        A data model for associating branches with releases.
    """
    __tablename__ = 'project_release_branches'

    __table_args__ = (
        UniqueConstraint('prelease_id', 'prepo_id', 'prelbranch_branch_name', name='uq_project_release_branch'),
        Index('ix_project_release_branches_release_repo', 'prelease_id', 'prepo_id'),
    )

    id = Column('prelbranch_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    release_id = Column('prelease_id', BigInteger, ForeignKey('project_releases.prelease_id'), nullable=False, index=True,
                        doc="Reference to the release")
    repository_id = Column('prepo_id', BigInteger, ForeignKey('project_repositories.prepo_id'), nullable=False, index=True,
                           doc="Reference to the repository")
    branch_name = Column('prelbranch_branch_name', VARCHAR(256), nullable=False,
                         doc="Name of the branch")
    description = Column('prelbranch_description', Text, nullable=True,
                         doc="Description of the branch association")
    created_at = Column('prelbranch_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the association was created")

    release = relationship('ProjectRelease', back_populates='branches', lazy='selectin')
    repository = relationship('ProjectRepository', back_populates='release_branches', lazy='selectin')


class ProjectMergeEvent(PychestrateModelBase, SerializableModel):
    """
        A data model for storing scheduled merge events.
    """
    __tablename__ = 'project_merge_events'

    __table_args__ = (
        Index('ix_project_merge_events_project_time', 'proj_id', 'pmerge_scheduled_time'),
        Index('ix_project_merge_events_release', 'prelease_id'),
        Index('ix_project_merge_events_status', 'pmerge_status'),
    )

    id = Column('pmerge_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    project_id = Column('proj_id', BigInteger, ForeignKey('projects.proj_id'), nullable=False, index=True,
                        doc="Reference to the project")
    release_id = Column('prelease_id', BigInteger, ForeignKey('project_releases.prelease_id'), nullable=False, index=True,
                        doc="Reference to the release")
    repository_id = Column('prepo_id', BigInteger, ForeignKey('project_repositories.prepo_id'), nullable=False, index=True,
                           doc="Reference to the repository")
    source_branch = Column('pmerge_source_branch', VARCHAR(256), nullable=False,
                           doc="Source branch for the merge")
    target_branch = Column('pmerge_target_branch', VARCHAR(256), nullable=False,
                           doc="Target branch for the merge")
    name = Column('pmerge_name', VARCHAR(256), nullable=False,
                  doc="Name of the merge event")
    description = Column('pmerge_description', Text, nullable=True,
                         doc="Description of the merge event")
    scheduled_time = Column('pmerge_scheduled_time', UtcDateTime(timezone=True), nullable=False,
                            doc="Scheduled time for the merge")
    status = Column('pmerge_status', VARCHAR(32), default='scheduled', nullable=False,
                    doc="Status of the merge event (scheduled, in_progress, completed, failed)")
    executed_at = Column('pmerge_executed_at', UtcDateTime(timezone=True), nullable=True,
                         doc="Timestamp when the merge was executed")
    executed_by_id = Column('pmerge_executed_by_id', UUIDType, ForeignKey('user.user_id'), nullable=True,
                            doc="Reference to the user who executed the merge")
    error_message = Column('pmerge_error_message', Text, nullable=True,
                           doc="Error message if the merge failed")
    created_at = Column('pmerge_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the event was created")
    updated_at = Column('pmerge_updated_at', UtcDateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False,
                        doc="Timestamp when the event was last updated")

    release = relationship('ProjectRelease', back_populates='merge_events', lazy='selectin')
    repository = relationship('ProjectRepository', back_populates='merge_events', lazy='selectin')


class ProjectPullEvent(PychestrateModelBase, SerializableModel):
    """
        A data model for storing scheduled pull events.
    """
    __tablename__ = 'project_pull_events'

    __table_args__ = (
        Index('ix_project_pull_events_project_time', 'proj_id', 'ppull_scheduled_time'),
        Index('ix_project_pull_events_release', 'prelease_id'),
        Index('ix_project_pull_events_status', 'ppull_status'),
    )

    id = Column('ppull_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    project_id = Column('proj_id', BigInteger, ForeignKey('projects.proj_id'), nullable=False, index=True,
                        doc="Reference to the project")
    release_id = Column('prelease_id', BigInteger, ForeignKey('project_releases.prelease_id'), nullable=False, index=True,
                        doc="Reference to the release")
    repository_id = Column('prepo_id', BigInteger, ForeignKey('project_repositories.prepo_id'), nullable=False, index=True,
                           doc="Reference to the repository")
    source_branch = Column('ppull_source_branch', VARCHAR(256), nullable=False,
                           doc="Source branch for the pull")
    target_branch = Column('ppull_target_branch', VARCHAR(256), nullable=False,
                           doc="Target branch for the pull")
    name = Column('ppull_name', VARCHAR(256), nullable=False,
                  doc="Name of the pull event")
    description = Column('ppull_description', Text, nullable=True,
                         doc="Description of the pull event")
    scheduled_time = Column('ppull_scheduled_time', UtcDateTime(timezone=True), nullable=False,
                            doc="Scheduled time for the pull")
    status = Column('ppull_status', VARCHAR(32), default='scheduled', nullable=False,
                    doc="Status of the pull event (scheduled, in_progress, completed, failed)")
    executed_at = Column('ppull_executed_at', UtcDateTime(timezone=True), nullable=True,
                         doc="Timestamp when the pull was executed")
    executed_by_id = Column('ppull_executed_by_id', UUIDType, ForeignKey('user.user_id'), nullable=True,
                            doc="Reference to the user who executed the pull")
    error_message = Column('ppull_error_message', Text, nullable=True,
                           doc="Error message if the pull failed")
    created_at = Column('ppull_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the event was created")
    updated_at = Column('ppull_updated_at', UtcDateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False,
                        doc="Timestamp when the event was last updated")

    release = relationship('ProjectRelease', back_populates='pull_events', lazy='selectin')
    repository = relationship('ProjectRepository', back_populates='pull_events', lazy='selectin')



class ProjectWatchTriggerSource(str, enum.Enum):
    """
        Enum-like class to represent the trigger sources for watches.
    """
    REPOSITORY_COMMIT = 'repository_commit'
    REPOSITORY_TAG = 'repository_tag'
    REPOSITORY_BRANCH = 'repository_branch'
    BUILD_COMPLETION = 'build_completion'


class ProjectWatchAction(str, enum.Enum):
    """
        Enum-like class to represent the actions that can be triggered by watches.
    """
    TRIGGER_BUILD = 'trigger_build'
    TRIGGER_INFRA_JOB = 'trigger_infra_job'
    TRIGGER_TEST_JOB = 'trigger_test_job'
    TRIGGER_PIPELINE = 'trigger_pipeline'
    SEND_NOTIFICATION = 'send_notification'


class ProjectWatch(PychestrateModelBase, SerializableModel):
    """
        A data model for storing watch configurations.
        Watches monitor repositories and builds to trigger automated actions.
    """
    __tablename__ = 'project_watches'

    __table_args__ = (
        UniqueConstraint('proj_id', 'pwatch_name', name='uq_project_watch_name'),
        Index('ix_project_watches_project_name', 'proj_id', 'pwatch_name'),
        Index('ix_project_watches_source', 'pwatch_trigger_source', 'pwatch_source_id'),
    )

    id = Column('pwatch_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    project_id = Column('proj_id', BigInteger, ForeignKey('projects.proj_id'), nullable=False, index=True,
                        doc="Reference to the project")
    name = Column('pwatch_name', VARCHAR(128), nullable=False,
                  doc="Name of the watch (unique within project)")
    trigger_source = Column('pwatch_trigger_source', VARCHAR(32), nullable=False,
                            doc="Source of trigger events (repository_commit, repository_tag, repository_branch, build_completion)")
    source_id = Column('pwatch_source_id', BigInteger, nullable=False,
                       doc="ID of the source (repository_id or build_spec_id)")
    repository_id = Column('prepo_id', BigInteger, ForeignKey('project_repositories.prepo_id'), nullable=True, index=True,
                           doc="Reference to the repository (for repository-based triggers)")
    conditions_json = Column('pwatch_conditions_json', JSON, default={}, nullable=False,
                             doc="JSON-encoded conditions for triggering (branch_pattern, tag_pattern, file_pattern, build_status)")
    actions_json = Column('pwatch_actions_json', JSON, default=[], nullable=False,
                          doc="JSON-encoded list of actions to execute when triggered")
    enabled = Column('pwatch_enabled', Boolean, default=True, nullable=False,
                     doc="Flag indicating if the watch is enabled")
    description = Column('pwatch_description', VARCHAR(512), nullable=True,
                         doc="Human-readable description of the watch")
    last_trigger_time = Column('pwatch_last_trigger_time', UtcDateTime(timezone=True), nullable=True,
                               doc="Timestamp of the last trigger")
    trigger_count = Column('pwatch_trigger_count', Integer, default=0, nullable=False,
                           doc="Number of times the watch has been triggered")
    created_at = Column('pwatch_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the watch was created")
    updated_at = Column('pwatch_updated_at', UtcDateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False,
                        doc="Timestamp when the watch was last updated")

    project = relationship('Project', back_populates='watches', lazy='selectin')
    repository = relationship('ProjectRepository', back_populates='watches', lazy='selectin')
    trigger_logs = relationship('ProjectWatchTriggerLog', back_populates='watch', cascade='all, delete-orphan', lazy='selectin')


class ProjectWatchTriggerLog(PychestrateModelBase, SerializableModel):
    """
        A data model for storing watch trigger logs.
        Logs record each time a watch is triggered and the actions executed.
    """
    __tablename__ = 'project_watch_trigger_logs'

    id = Column('pwatchlog_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    watch_id = Column('pwatch_id', BigInteger, ForeignKey('project_watches.pwatch_id'), nullable=False, index=True,
                      doc="Reference to the watch")
    triggered_at = Column('pwatchlog_triggered_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                          doc="Timestamp when the watch was triggered")
    trigger_event_json = Column('pwatchlog_trigger_event_json', JSON, nullable=False,
                                doc="JSON-encoded event data that triggered the watch")
    actions_executed_json = Column('pwatchlog_actions_executed_json', JSON, default=[], nullable=False,
                                   doc="JSON-encoded list of actions that were executed")
    success = Column('pwatchlog_success', Boolean, nullable=False,
                     doc="Flag indicating if all actions succeeded")
    error_message = Column('pwatchlog_error_message', Text, nullable=True,
                           doc="Error message if any action failed")

    watch = relationship('ProjectWatch', back_populates='trigger_logs', lazy='selectin')


class ProjectReleaseTemplate(PychestrateModelBase, SerializableModel):
    """
        A data model for storing project-scoped release templates.

        A release template captures the default values that should be
        used when creating a new release within a project. Templates
        are project-scoped — the same template name may exist across
        different projects.
    """

    __tablename__ = 'project_release_templates'

    __table_args__ = (
        UniqueConstraint('proj_id', 'rtmpl_name', name='uq_project_release_template_name'),
        Index('ix_project_release_templates_project', 'proj_id'),
    )

    id = Column('rtmpl_id', BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    project_id = Column('proj_id', BigInteger, ForeignKey('projects.proj_id', ondelete='CASCADE'),
                        nullable=False, index=True,
                        doc="Reference to the owning project")
    name = Column('rtmpl_name', VARCHAR(128), nullable=False,
                  doc="Template name; unique within a project")
    description = Column('rtmpl_description', Text, nullable=True,
                         doc="Human-readable description of the template")
    default_channel = Column('rtmpl_default_channel', VARCHAR(128), nullable=True,
                             doc="Default release channel applied when creating from this template")
    version_pattern = Column('rtmpl_version_pattern', VARCHAR(128), nullable=True,
                             doc="Default version pattern (regex or semver pattern)")
    default_repo_ids = Column('rtmpl_default_repo_ids', JSON, default=list, nullable=False,
                              doc="JSON-encoded list of default repository IDs")
    default_pipeline = Column('rtmpl_default_pipeline', JSON, nullable=True,
                              doc="JSON-encoded default pipeline blob")
    default_schedule = Column('rtmpl_default_schedule', JSON, nullable=True,
                              doc="JSON-encoded default schedule blob")
    created_at = Column('rtmpl_created_at', UtcDateTime(timezone=True), default=utc_now, nullable=False,
                        doc="Timestamp when the template was created")
    updated_at = Column('rtmpl_updated_at', UtcDateTime(timezone=True), default=utc_now, onupdate=utc_now,
                        nullable=False, doc="Timestamp when the template was last updated")

    project = relationship('Project', back_populates='release_templates', lazy='selectin')