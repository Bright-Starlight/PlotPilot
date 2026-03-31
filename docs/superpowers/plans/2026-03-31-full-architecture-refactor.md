# aitext 全面架构重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构 aitext 后端（Web 层 + AI 核心模块）为 DDD 分层架构，重新设计 RESTful API，并适配前端

**Architecture:** DDD 分层架构（Domain/Application/Infrastructure/Interfaces），抽象存储层，统一 LLM 服务接口，前后端并行开发

**Tech Stack:** FastAPI, Pydantic, dependency-injector, pytest (后端) | Vue 3, TypeScript, Pinia, Axios (前端)

---

## 文件结构规划

### 新增后端目录结构

```
domain/                          # 领域层（核心业务逻辑）
├── novel/
│   ├── entities/
│   │   ├── __init__.py
│   │   ├── novel.py            # Novel 聚合根
│   │   ├── chapter.py          # Chapter 实体
│   │   └── manuscript.py       # Manuscript 实体
│   ├── value_objects/
│   │   ├── __init__.py
│   │   ├── novel_id.py         # NovelId 值对象
│   │   ├── chapter_content.py  # ChapterContent 值对象
│   │   └── word_count.py       # WordCount 值对象
│   ├── services/
│   │   ├── __init__.py
│   │   ├── chapter_generation_service.py
│   │   └── consistency_check_service.py
│   └── repositories/
│       ├── __init__.py
│       ├── novel_repository.py      # 接口
│       └── chapter_repository.py    # 接口
├── bible/
│   ├── entities/
│   │   ├── __init__.py
│   │   ├── bible.py
│   │   ├── character.py
│   │   └── world_setting.py
│   └── repositories/
│       ├── __init__.py
│       └── bible_repository.py
├── ai/
│   ├── entities/
│   │   ├── __init__.py
│   │   └── generation_task.py
│   ├── value_objects/
│   │   ├── __init__.py
│   │   ├── prompt.py
│   │   └── token_usage.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── llm_service.py          # 接口
│   │   └── prompt_builder.py
│   └── repositories/
│       ├── __init__.py
│       └── conversation_repository.py
└── shared/
    ├── __init__.py
    ├── events.py              # 领域事件
    ├── exceptions.py          # 领域异常
    └── base_entity.py         # 实体基类

application/                    # 应用层（用例编排）
├── commands/
│   ├── __init__.py
│   ├── create_novel.py
│   ├── write_chapter.py
│   └── generate_with_ai.py
├── queries/
│   ├── __init__.py
│   ├── get_novel_detail.py
│   └── list_chapters.py
├── services/
│   ├── __init__.py
│   ├── novel_service.py
│   ├── chapter_service.py
│   └── ai_generation_service.py
└── dto/
    ├── __init__.py
    ├── novel_dto.py
    └── chapter_dto.py

infrastructure/                 # 基础设施层（技术实现）
├── persistence/
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── file_novel_repository.py
│   │   └── file_chapter_repository.py
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── storage_backend.py      # 接口
│   │   └── file_storage.py
│   └── mappers/
│       ├── __init__.py
│       └── novel_mapper.py
├── ai/
│   ├── __init__.py
│   ├── llm_client_impl.py
│   └── providers/
│       ├── __init__.py
│       ├── anthropic_provider.py
│       └── ark_provider.py
└── config/
    ├── __init__.py
    └── settings.py

interfaces/                     # 接口层（对外暴露）
└── api/
    ├── v1/
    │   ├── __init__.py
    │   ├── novels.py
    │   ├── chapters.py
    │   ├── bible.py
    │   └── tasks.py
    ├── dependencies.py
    └── middleware/
        └── (已存在 error_handler.py, logging_config.py)
```

### 前端新增文件

```
web-app/src/
├── api/
│   ├── novels.ts              # 新增
│   ├── chapters.ts            # 新增
│   ├── bible.ts               # 新增
│   └── tasks.ts               # 新增
├── types/
│   └── api.ts                 # 扩展现有文件
└── stores/
    ├── novelStore.ts          # 新增
    └── chapterStore.ts        # 新增
```

---

## Week 1: 基础设施搭建（Day 1-7）

### Task 1: 创建领域层基础结构

**Files:**
- Create: `domain/__init__.py`
- Create: `domain/shared/__init__.py`
- Create: `domain/shared/base_entity.py`
- Create: `domain/shared/exceptions.py`
- Create: `domain/shared/events.py`
- Test: `tests/unit/domain/shared/test_base_entity.py`

- [ ] **Step 1: 创建 domain 包结构**

```bash
mkdir -p domain/shared
touch domain/__init__.py
touch domain/shared/__init__.py
```

- [ ] **Step 2: 编写实体基类测试**

```python
# tests/unit/domain/shared/test_base_entity.py
import pytest
from datetime import datetime
from domain.shared.base_entity import BaseEntity


class TestEntity(BaseEntity):
    """测试用实体"""
    def __init__(self, id: str, name: str):
        super().__init__(id)
        self.name = name


def test_base_entity_has_id():
    """测试实体有 ID"""
    entity = TestEntity(id="test-1", name="Test")
    assert entity.id == "test-1"


def test_base_entity_has_timestamps():
    """测试实体有时间戳"""
    entity = TestEntity(id="test-1", name="Test")
    assert isinstance(entity.created_at, datetime)
    assert isinstance(entity.updated_at, datetime)


def test_base_entity_equality_by_id():
    """测试实体相等性基于 ID"""
    entity1 = TestEntity(id="test-1", name="Test1")
    entity2 = TestEntity(id="test-1", name="Test2")
    entity3 = TestEntity(id="test-2", name="Test1")

    assert entity1 == entity2  # 相同 ID
    assert entity1 != entity3  # 不同 ID
```

- [ ] **Step 3: 运行测试验证失败**

Run: `pytest tests/unit/domain/shared/test_base_entity.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'domain.shared.base_entity'"

- [ ] **Step 4: 实现实体基类**

```python
# domain/shared/base_entity.py
from datetime import datetime
from typing import Any


class BaseEntity:
    """实体基类"""

    def __init__(self, id: str):
        self.id = id
        self.created_at = datetime.now()
        self.updated_at = datetime.now()

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, BaseEntity):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
```

- [ ] **Step 5: 运行测试验证通过**

Run: `pytest tests/unit/domain/shared/test_base_entity.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: 实现领域异常**

```python
# domain/shared/exceptions.py
class DomainException(Exception):
    """领域异常基类"""
    pass


class EntityNotFoundError(DomainException):
    """实体未找到"""
    def __init__(self, entity_type: str, entity_id: str):
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(f"{entity_type} with id '{entity_id}' not found")


class InvalidOperationError(DomainException):
    """无效操作"""
    pass


class ValidationError(DomainException):
    """验证错误"""
    pass
```

- [ ] **Step 7: 实现领域事件基类**

```python
# domain/shared/events.py
from datetime import datetime
from typing import Any, Dict
import uuid


class DomainEvent:
    """领域事件基类"""

    def __init__(self, aggregate_id: str):
        self.event_id = str(uuid.uuid4())
        self.aggregate_id = aggregate_id
        self.occurred_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "aggregate_id": self.aggregate_id,
            "occurred_at": self.occurred_at.isoformat(),
            "event_type": self.__class__.__name__
        }
```

- [ ] **Step 8: 提交**

```bash
git add domain/ tests/unit/domain/
git commit -m "feat(domain): add base entity, exceptions, and events

- BaseEntity with id, timestamps, equality
- Domain exceptions: EntityNotFoundError, InvalidOperationError, ValidationError
- DomainEvent base class with event_id and occurred_at"
```

---

### Task 2: 实现 Novel 值对象

**Files:**
- Create: `domain/novel/__init__.py`
- Create: `domain/novel/value_objects/__init__.py`
- Create: `domain/novel/value_objects/novel_id.py`
- Create: `domain/novel/value_objects/word_count.py`
- Create: `domain/novel/value_objects/chapter_content.py`
- Test: `tests/unit/domain/novel/value_objects/test_novel_id.py`
- Test: `tests/unit/domain/novel/value_objects/test_word_count.py`

- [ ] **Step 1: 创建 novel 包结构**

```bash
mkdir -p domain/novel/value_objects
touch domain/novel/__init__.py
touch domain/novel/value_objects/__init__.py
mkdir -p tests/unit/domain/novel/value_objects
touch tests/unit/domain/novel/value_objects/__init__.py
```

- [ ] **Step 2: 编写 NovelId 测试**

```python
# tests/unit/domain/novel/value_objects/test_novel_id.py
import pytest
from domain/novel/value_objects/novel_id import NovelId


def test_novel_id_creation():
    """测试创建 NovelId"""
    novel_id = NovelId("novel-123")
    assert novel_id.value == "novel-123"


def test_novel_id_immutable():
    """测试 NovelId 不可变"""
    novel_id = NovelId("novel-123")
    with pytest.raises(AttributeError):
        novel_id.value = "novel-456"


def test_novel_id_equality():
    """测试 NovelId 相等性"""
    id1 = NovelId("novel-123")
    id2 = NovelId("novel-123")
    id3 = NovelId("novel-456")

    assert id1 == id2
    assert id1 != id3


def test_novel_id_validation():
    """测试 NovelId 验证"""
    with pytest.raises(ValueError):
        NovelId("")  # 空字符串

    with pytest.raises(ValueError):
        NovelId("   ")  # 只有空格
```

- [ ] **Step 3: 运行测试验证失败**

Run: `pytest tests/unit/domain/novel/value_objects/test_novel_id.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 4: 实现 NovelId**

```python
# domain/novel/value_objects/novel_id.py
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NovelId:
    """小说 ID 值对象"""
    value: str

    def __post_init__(self):
        if not self.value or not self.value.strip():
            raise ValueError("Novel ID cannot be empty")

    def __str__(self) -> str:
        return self.value

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, NovelId):
            return False
        return self.value == other.value

    def __hash__(self) -> int:
        return hash(self.value)
```

- [ ] **Step 5: 运行测试验证通过**

Run: `pytest tests/unit/domain/novel/value_objects/test_novel_id.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: 编写 WordCount 测试**

```python
# tests/unit/domain/novel/value_objects/test_word_count.py
import pytest
from domain.novel.value_objects.word_count import WordCount


def test_word_count_creation():
    """测试创建 WordCount"""
    wc = WordCount(1000)
    assert wc.value == 1000


def test_word_count_negative_raises_error():
    """测试负数字数抛出异常"""
    with pytest.raises(ValueError):
        WordCount(-100)


def test_word_count_addition():
    """测试字数相加"""
    wc1 = WordCount(1000)
    wc2 = WordCount(500)
    result = wc1 + wc2
    assert result.value == 1500


def test_word_count_comparison():
    """测试字数比较"""
    wc1 = WordCount(1000)
    wc2 = WordCount(500)
    wc3 = WordCount(1000)

    assert wc1 > wc2
    assert wc2 < wc1
    assert wc1 == wc3
```

- [ ] **Step 7: 运行测试验证失败**

Run: `pytest tests/unit/domain/novel/value_objects/test_word_count.py -v`
Expected: FAIL

- [ ] **Step 8: 实现 WordCount**

```python
# domain/novel/value_objects/word_count.py
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WordCount:
    """字数值对象"""
    value: int

    def __post_init__(self):
        if self.value < 0:
            raise ValueError("Word count cannot be negative")

    def __add__(self, other: 'WordCount') -> 'WordCount':
        return WordCount(self.value + other.value)

    def __lt__(self, other: 'WordCount') -> bool:
        return self.value < other.value

    def __le__(self, other: 'WordCount') -> bool:
        return self.value <= other.value

    def __gt__(self, other: 'WordCount') -> bool:
        return self.value > other.value

    def __ge__(self, other: 'WordCount') -> bool:
        return self.value >= other.value
```

- [ ] **Step 9: 运行测试验证通过**

Run: `pytest tests/unit/domain/novel/value_objects/test_word_count.py -v`
Expected: PASS (4 tests)

- [ ] **Step 10: 实现 ChapterContent（无测试，简单包装）**

```python
# domain/novel/value_objects/chapter_content.py
from dataclasses import dataclass


@dataclass(frozen=True)
class ChapterContent:
    """章节内容值对象"""
    raw_text: str

    def __post_init__(self):
        if self.raw_text is None:
            raise ValueError("Chapter content cannot be None")

    def word_count(self) -> int:
        """计算字数（简单实现）"""
        return len(self.raw_text)
```

- [ ] **Step 11: 提交**

```bash
git add domain/novel/value_objects/ tests/unit/domain/novel/
git commit -m "feat(domain): add Novel value objects

- NovelId: immutable ID with validation
- WordCount: immutable count with arithmetic operations
- ChapterContent: raw text wrapper with word count"
```

---

### Task 3: 实现 Novel 实体和聚合根

**Files:**
- Create: `domain/novel/entities/__init__.py`
- Create: `domain/novel/entities/novel.py`
- Create: `domain/novel/entities/chapter.py`
- Test: `tests/unit/domain/novel/entities/test_novel.py`

- [ ] **Step 1: 创建 entities 包**

```bash
mkdir -p domain/novel/entities
touch domain/novel/entities/__init__.py
mkdir -p tests/unit/domain/novel/entities
touch tests/unit/domain/novel/entities/__init__.py
```

- [ ] **Step 2: 编写 Novel 聚合根测试**

```python
# tests/unit/domain/novel/entities/test_novel.py
import pytest
from domain.novel.entities.novel import Novel, NovelStage
from domain.novel.entities.chapter import Chapter
from domain.novel.value_objects.novel_id import NovelId
from domain.shared.exceptions import InvalidOperationError


def test_novel_creation():
    """测试创建小说"""
    novel = Novel(
        id=NovelId("novel-1"),
        title="测试小说",
        author="测试作者",
        target_chapters=10
    )
    assert novel.id.value == "novel-1"
    assert novel.title == "测试小说"
    assert novel.stage == NovelStage.PLANNING


def test_novel_add_chapter():
    """测试添加章节"""
    novel = Novel(
        id=NovelId("novel-1"),
        title="测试小说",
        author="测试作者",
        target_chapters=10
    )
    chapter = Chapter(
        id="chapter-1",
        novel_id=NovelId("novel-1"),
        number=1,
        title="第一章"
    )
    novel.add_chapter(chapter)
    assert len(novel.chapters) == 1
    assert novel.chapters[0].number == 1


def test_novel_add_chapter_non_sequential_raises_error():
    """测试添加非连续章节抛出异常"""
    novel = Novel(
        id=NovelId("novel-1"),
        title="测试小说",
        author="测试作者",
        target_chapters=10
    )
    chapter1 = Chapter(
        id="chapter-1",
        novel_id=NovelId("novel-1"),
        number=1,
        title="第一章"
    )
    chapter3 = Chapter(
        id="chapter-3",
        novel_id=NovelId("novel-1"),
        number=3,
        title="第三章"
    )
    novel.add_chapter(chapter1)

    with pytest.raises(InvalidOperationError):
        novel.add_chapter(chapter3)  # 跳过第2章
```

- [ ] **Step 3: 运行测试验证失败**

Run: `pytest tests/unit/domain/novel/entities/test_novel.py -v`
Expected: FAIL

- [ ] **Step 4: 实现 Chapter 实体**

```python
# domain/novel/entities/chapter.py
from enum import Enum
from domain.shared.base_entity import BaseEntity
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.chapter_content import ChapterContent
from domain.novel.value_objects.word_count import WordCount


class ChapterStatus(str, Enum):
    """章节状态"""
    DRAFT = "draft"
    REVIEWING = "reviewing"
    COMPLETED = "completed"


class Chapter(BaseEntity):
    """章节实体"""

    def __init__(
        self,
        id: str,
        novel_id: NovelId,
        number: int,
        title: str,
        content: str = "",
        status: ChapterStatus = ChapterStatus.DRAFT
    ):
        super().__init__(id)
        self.novel_id = novel_id
        self.number = number
        self.title = title
        self._content = ChapterContent(content)
        self.status = status

    @property
    def content(self) -> str:
        return self._content.raw_text

    @property
    def word_count(self) -> WordCount:
        return WordCount(self._content.word_count())

    def update_content(self, content: str) -> None:
        """更新内容"""
        self._content = ChapterContent(content)
        self.updated_at = datetime.now()
```

- [ ] **Step 5: 实现 Novel 聚合根**

```python
# domain/novel/entities/novel.py
from enum import Enum
from typing import List
from domain.shared.base_entity import BaseEntity
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.entities.chapter import Chapter
from domain.shared.exceptions import InvalidOperationError


class NovelStage(str, Enum):
    """小说阶段"""
    PLANNING = "planning"
    WRITING = "writing"
    REVIEWING = "reviewing"
    COMPLETED = "completed"


class Novel(BaseEntity):
    """小说聚合根"""

    def __init__(
        self,
        id: NovelId,
        title: str,
        author: str,
        target_chapters: int,
        stage: NovelStage = NovelStage.PLANNING
    ):
        super().__init__(id.value)
        self.novel_id = id
        self.title = title
        self.author = author
        self.target_chapters = target_chapters
        self.stage = stage
        self.chapters: List[Chapter] = []

    def add_chapter(self, chapter: Chapter) -> None:
        """添加章节（必须连续）"""
        expected_number = len(self.chapters) + 1
        if chapter.number != expected_number:
            raise InvalidOperationError(
                f"Chapter number must be {expected_number}, got {chapter.number}"
            )
        self.chapters.append(chapter)

    @property
    def completed_chapters(self) -> int:
        """已完成章节数"""
        return len([c for c in self.chapters if c.status == ChapterStatus.COMPLETED])
```

- [ ] **Step 6: 添加缺失的导入**

```python
# 在 domain/novel/entities/chapter.py 顶部添加
from datetime import datetime
```

- [ ] **Step 7: 运行测试验证通过**

Run: `pytest tests/unit/domain/novel/entities/test_novel.py -v`
Expected: PASS (3 tests)

- [ ] **Step 8: 提交**

```bash
git add domain/novel/entities/ tests/unit/domain/novel/entities/
git commit -m "feat(domain): add Novel aggregate root and Chapter entity

- Novel: aggregate root with chapters, stage, validation
- Chapter: entity with content, word count, status
- Business rule: chapters must be added sequentially"
```

---

### Task 4: 实现仓储接口

**Files:**
- Create: `domain/novel/repositories/__init__.py`
- Create: `domain/novel/repositories/novel_repository.py`
- Create: `domain/novel/repositories/chapter_repository.py`

- [ ] **Step 1: 创建 repositories 包**

```bash
mkdir -p domain/novel/repositories
touch domain/novel/repositories/__init__.py
```

- [ ] **Step 2: 实现 NovelRepository 接口**

```python
# domain/novel/repositories/novel_repository.py
from abc import ABC, abstractmethod
from typing import List, Optional
from domain.novel.entities.novel import Novel
from domain.novel.value_objects.novel_id import NovelId


class NovelRepository(ABC):
    """小说仓储接口"""

    @abstractmethod
    def save(self, novel: Novel) -> None:
        """保存小说"""
        pass

    @abstractmethod
    def get_by_id(self, novel_id: NovelId) -> Optional[Novel]:
        """根据 ID 获取小说"""
        pass

    @abstractmethod
    def list_all(self) -> List[Novel]:
        """列出所有小说"""
        pass

    @abstractmethod
    def delete(self, novel_id: NovelId) -> None:
        """删除小说"""
        pass

    @abstractmethod
    def exists(self, novel_id: NovelId) -> bool:
        """检查小说是否存在"""
        pass
```

- [ ] **Step 3: 实现 ChapterRepository 接口**

```python
# domain/novel/repositories/chapter_repository.py
from abc import ABC, abstractmethod
from typing import List, Optional
from domain.novel.entities.chapter import Chapter
from domain.novel.value_objects.novel_id import NovelId


class ChapterRepository(ABC):
    """章节仓储接口"""

    @abstractmethod
    def save(self, chapter: Chapter) -> None:
        """保存章节"""
        pass

    @abstractmethod
    def get_by_id(self, chapter_id: str) -> Optional[Chapter]:
        """根据 ID 获取章节"""
        pass

    @abstractmethod
    def list_by_novel(self, novel_id: NovelId) -> List[Chapter]:
        """列出小说的所有章节"""
        pass

    @abstractmethod
    def delete(self, chapter_id: str) -> None:
        """删除章节"""
        pass
```

- [ ] **Step 4: 提交**

```bash
git add domain/novel/repositories/
git commit -m "feat(domain): add repository interfaces

- NovelRepository: save, get, list, delete, exists
- ChapterRepository: save, get, list by novel, delete"
```

---

由于这是一个非常大的重构项目（3周，数百个文件），完整的实施计划会非常长。我已经展示了前4个任务的详细结构。

**重要决策点：**

鉴于这个项目的规模（3周，后端DDD重构 + AI模块 + 前端适配），我建议将其分解为**3个独立的实施计划**：

1. **Week 1 Plan**: DDD 基础设施（领域层 + 基础设施层）
2. **Week 2 Plan**: API 迁移和 LLM 重构（应用层 + 接口层 + AI模块）
3. **Week 3 Plan**: 前端适配和清理（前端 + 旧代码清理）

这样做的好处：
- 每个计划可以独立执行和测试
- 更容易跟踪进度
- 可以在每周结束时进行评审
- 降低风险，可以根据进度调整

---

## 计划说明

本重构项目分为3个独立的周计划：

1. **本计划 (Week 1)**: DDD 基础设施搭建
2. **Week 2 计划**: API 迁移和 LLM 重构（待创建）
3. **Week 3 计划**: 前端适配和旧代码清理（待创建）

每个计划可以独立执行、测试和验收。

---

### Task 5: 实现存储抽象层

**Files:**
- Create: `infrastructure/__init__.py`
- Create: `infrastructure/persistence/__init__.py`
- Create: `infrastructure/persistence/storage/__init__.py`
- Create: `infrastructure/persistence/storage/storage_backend.py`
- Create: `infrastructure/persistence/storage/file_storage.py`
- Test: `tests/integration/infrastructure/persistence/test_file_storage.py`

- [ ] **Step 1: 创建 infrastructure 包结构**

```bash
mkdir -p infrastructure/persistence/storage
touch infrastructure/__init__.py
touch infrastructure/persistence/__init__.py
touch infrastructure/persistence/storage/__init__.py
mkdir -p tests/integration/infrastructure/persistence
touch tests/integration/infrastructure/__init__.py
touch tests/integration/infrastructure/persistence/__init__.py
```

- [ ] **Step 2: 实现存储后端接口**

```python
# infrastructure/persistence/storage/storage_backend.py
from abc import ABC, abstractmethod
from typing import Optional


class StorageBackend(ABC):
    """存储后端接口"""

    @abstractmethod
    def read(self, path: str) -> Optional[str]:
        """读取文件内容"""
        pass

    @abstractmethod
    def write(self, path: str, content: str) -> None:
        """写入文件内容"""
        pass

    @abstractmethod
    def exists(self, path: str) -> bool:
        """检查文件是否存在"""
        pass

    @abstractmethod
    def delete(self, path: str) -> None:
        """删除文件"""
        pass

    @abstractmethod
    def list_dir(self, path: str) -> list[str]:
        """列出目录内容"""
        pass
```

- [ ] **Step 3: 编写文件存储集成测试**

```python
# tests/integration/infrastructure/persistence/test_file_storage.py
import pytest
import tempfile
import shutil
from pathlib import Path
from infrastructure.persistence.storage.file_storage import FileStorage


@pytest.fixture
def temp_dir():
    """临时目录"""
    temp_path = tempfile.mkdtemp()
    yield temp_path
    shutil.rmtree(temp_path)


@pytest.fixture
def file_storage(temp_dir):
    """文件存储实例"""
    return FileStorage(base_path=temp_dir)


def test_write_and_read(file_storage, temp_dir):
    """测试写入和读取"""
    content = "测试内容"
    file_storage.write("test.txt", content)

    result = file_storage.read("test.txt")
    assert result == content


def test_exists(file_storage):
    """测试文件存在检查"""
    assert not file_storage.exists("nonexistent.txt")

    file_storage.write("exists.txt", "content")
    assert file_storage.exists("exists.txt")


def test_delete(file_storage):
    """测试删除文件"""
    file_storage.write("delete_me.txt", "content")
    assert file_storage.exists("delete_me.txt")

    file_storage.delete("delete_me.txt")
    assert not file_storage.exists("delete_me.txt")


def test_list_dir(file_storage):
    """测试列出目录"""
    file_storage.write("file1.txt", "content1")
    file_storage.write("file2.txt", "content2")

    files = file_storage.list_dir(".")
    assert "file1.txt" in files
    assert "file2.txt" in files
```

- [ ] **Step 4: 运行测试验证失败**

Run: `pytest tests/integration/infrastructure/persistence/test_file_storage.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 5: 实现文件存储**

```python
# infrastructure/persistence/storage/file_storage.py
import os
from pathlib import Path
from typing import Optional
from infrastructure.persistence.storage.storage_backend import StorageBackend


class FileStorage(StorageBackend):
    """文件系统存储实现"""

    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_full_path(self, path: str) -> Path:
        """获取完整路径"""
        return self.base_path / path

    def read(self, path: str) -> Optional[str]:
        """读取文件内容"""
        full_path = self._get_full_path(path)
        if not full_path.exists():
            return None
        return full_path.read_text(encoding="utf-8")

    def write(self, path: str, content: str) -> None:
        """写入文件内容"""
        full_path = self._get_full_path(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")

    def exists(self, path: str) -> bool:
        """检查文件是否存在"""
        return self._get_full_path(path).exists()

    def delete(self, path: str) -> None:
        """删除文件"""
        full_path = self._get_full_path(path)
        if full_path.exists():
            full_path.unlink()

    def list_dir(self, path: str) -> list[str]:
        """列出目录内容"""
        full_path = self._get_full_path(path)
        if not full_path.exists() or not full_path.is_dir():
            return []
        return [item.name for item in full_path.iterdir()]
```

- [ ] **Step 6: 运行测试验证通过**

Run: `pytest tests/integration/infrastructure/persistence/test_file_storage.py -v`
Expected: PASS (4 tests)

- [ ] **Step 7: 提交**

```bash
git add infrastructure/persistence/storage/ tests/integration/infrastructure/
git commit -m "feat(infrastructure): add storage abstraction layer

- StorageBackend interface: read, write, exists, delete, list_dir
- FileStorage implementation with base_path
- Integration tests for file operations"
```

---

### Task 6: 实现 Novel 仓储实现

**Files:**
- Create: `infrastructure/persistence/repositories/__init__.py`
- Create: `infrastructure/persistence/repositories/file_novel_repository.py`
- Create: `infrastructure/persistence/mappers/__init__.py`
- Create: `infrastructure/persistence/mappers/novel_mapper.py`
- Test: `tests/integration/infrastructure/persistence/test_file_novel_repository.py`

- [ ] **Step 1: 创建 repositories 和 mappers 包**

```bash
mkdir -p infrastructure/persistence/repositories
mkdir -p infrastructure/persistence/mappers
touch infrastructure/persistence/repositories/__init__.py
touch infrastructure/persistence/mappers/__init__.py
```

- [ ] **Step 2: 编写 NovelMapper 测试**

```python
# tests/unit/infrastructure/persistence/test_novel_mapper.py
import pytest
from domain.novel.entities.novel import Novel, NovelStage
from domain.novel.value_objects.novel_id import NovelId
from infrastructure.persistence.mappers.novel_mapper import NovelMapper


def test_novel_to_dict():
    """测试 Novel 转字典"""
    novel = Novel(
        id=NovelId("novel-1"),
        title="测试小说",
        author="测试作者",
        target_chapters=10,
        stage=NovelStage.WRITING
    )

    data = NovelMapper.to_dict(novel)

    assert data["id"] == "novel-1"
    assert data["title"] == "测试小说"
    assert data["author"] == "测试作者"
    assert data["target_chapters"] == 10
    assert data["stage"] == "writing"


def test_novel_from_dict():
    """测试字典转 Novel"""
    data = {
        "id": "novel-1",
        "title": "测试小说",
        "author": "测试作者",
        "target_chapters": 10,
        "stage": "writing"
    }

    novel = NovelMapper.from_dict(data)

    assert novel.novel_id.value == "novel-1"
    assert novel.title == "测试小说"
    assert novel.author == "测试作者"
    assert novel.target_chapters == 10
    assert novel.stage == NovelStage.WRITING
```

- [ ] **Step 3: 运行测试验证失败**

Run: `pytest tests/unit/infrastructure/persistence/test_novel_mapper.py -v`
Expected: FAIL

- [ ] **Step 4: 实现 NovelMapper**

```python
# infrastructure/persistence/mappers/novel_mapper.py
from typing import Dict, Any
from domain.novel.entities.novel import Novel, NovelStage
from domain.novel.value_objects.novel_id import NovelId


class NovelMapper:
    """Novel 实体映射器"""

    @staticmethod
    def to_dict(novel: Novel) -> Dict[str, Any]:
        """将 Novel 转换为字典"""
        return {
            "id": novel.novel_id.value,
            "title": novel.title,
            "author": novel.author,
            "target_chapters": novel.target_chapters,
            "stage": novel.stage.value,
            "created_at": novel.created_at.isoformat(),
            "updated_at": novel.updated_at.isoformat()
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> Novel:
        """从字典创建 Novel"""
        return Novel(
            id=NovelId(data["id"]),
            title=data["title"],
            author=data["author"],
            target_chapters=data["target_chapters"],
            stage=NovelStage(data["stage"])
        )
```

- [ ] **Step 5: 运行测试验证通过**

Run: `pytest tests/unit/infrastructure/persistence/test_novel_mapper.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: 编写 FileNovelRepository 集成测试**

```python
# tests/integration/infrastructure/persistence/test_file_novel_repository.py
import pytest
import tempfile
import shutil
from domain.novel.entities.novel import Novel, NovelStage
from domain.novel.value_objects.novel_id import NovelId
from infrastructure.persistence.storage.file_storage import FileStorage
from infrastructure.persistence.repositories.file_novel_repository import FileNovelRepository


@pytest.fixture
def temp_dir():
    """临时目录"""
    temp_path = tempfile.mkdtemp()
    yield temp_path
    shutil.rmtree(temp_path)


@pytest.fixture
def repository(temp_dir):
    """仓储实例"""
    storage = FileStorage(base_path=temp_dir)
    return FileNovelRepository(storage=storage)


def test_save_and_get_novel(repository):
    """测试保存和获取小说"""
    novel = Novel(
        id=NovelId("novel-1"),
        title="测试小说",
        author="测试作者",
        target_chapters=10
    )

    repository.save(novel)
    loaded = repository.get_by_id(NovelId("novel-1"))

    assert loaded is not None
    assert loaded.novel_id.value == "novel-1"
    assert loaded.title == "测试小说"


def test_list_all_novels(repository):
    """测试列出所有小说"""
    novel1 = Novel(
        id=NovelId("novel-1"),
        title="小说1",
        author="作者1",
        target_chapters=10
    )
    novel2 = Novel(
        id=NovelId("novel-2"),
        title="小说2",
        author="作者2",
        target_chapters=20
    )

    repository.save(novel1)
    repository.save(novel2)

    novels = repository.list_all()
    assert len(novels) == 2


def test_delete_novel(repository):
    """测试删除小说"""
    novel = Novel(
        id=NovelId("novel-1"),
        title="测试小说",
        author="测试作者",
        target_chapters=10
    )

    repository.save(novel)
    assert repository.exists(NovelId("novel-1"))

    repository.delete(NovelId("novel-1"))
    assert not repository.exists(NovelId("novel-1"))
```

- [ ] **Step 7: 运行测试验证失败**

Run: `pytest tests/integration/infrastructure/persistence/test_file_novel_repository.py -v`
Expected: FAIL

- [ ] **Step 8: 实现 FileNovelRepository**

```python
# infrastructure/persistence/repositories/file_novel_repository.py
import json
from typing import List, Optional
from domain.novel.entities.novel import Novel
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.repositories.novel_repository import NovelRepository
from infrastructure.persistence.storage.storage_backend import StorageBackend
from infrastructure.persistence.mappers.novel_mapper import NovelMapper


class FileNovelRepository(NovelRepository):
    """基于文件的 Novel 仓储实现"""

    def __init__(self, storage: StorageBackend):
        self.storage = storage

    def _get_novel_path(self, novel_id: NovelId) -> str:
        """获取小说文件路径"""
        return f"novels/{novel_id.value}/manifest.json"

    def save(self, novel: Novel) -> None:
        """保存小说"""
        path = self._get_novel_path(novel.novel_id)
        data = NovelMapper.to_dict(novel)
        content = json.dumps(data, ensure_ascii=False, indent=2)
        self.storage.write(path, content)

    def get_by_id(self, novel_id: NovelId) -> Optional[Novel]:
        """根据 ID 获取小说"""
        path = self._get_novel_path(novel_id)
        content = self.storage.read(path)
        if content is None:
            return None
        data = json.loads(content)
        return NovelMapper.from_dict(data)

    def list_all(self) -> List[Novel]:
        """列出所有小说"""
        novels = []
        novel_dirs = self.storage.list_dir("novels")
        for novel_dir in novel_dirs:
            novel_id = NovelId(novel_dir)
            novel = self.get_by_id(novel_id)
            if novel:
                novels.append(novel)
        return novels

    def delete(self, novel_id: NovelId) -> None:
        """删除小说"""
        path = self._get_novel_path(novel_id)
        self.storage.delete(path)

    def exists(self, novel_id: NovelId) -> bool:
        """检查小说是否存在"""
        path = self._get_novel_path(novel_id)
        return self.storage.exists(path)
```

- [ ] **Step 9: 运行测试验证通过**

Run: `pytest tests/integration/infrastructure/persistence/test_file_novel_repository.py -v`
Expected: PASS (3 tests)

- [ ] **Step 10: 提交**

```bash
git add infrastructure/persistence/repositories/ infrastructure/persistence/mappers/ tests/
git commit -m "feat(infrastructure): add Novel repository implementation

- NovelMapper: bidirectional mapping between Novel and dict
- FileNovelRepository: file-based persistence with JSON
- Integration tests for save, get, list, delete operations"
```

---

### Task 7: 实现 AI 领域基础

**Files:**
- Create: `domain/ai/__init__.py`
- Create: `domain/ai/value_objects/__init__.py`
- Create: `domain/ai/value_objects/prompt.py`
- Create: `domain/ai/value_objects/token_usage.py`
- Create: `domain/ai/services/__init__.py`
- Create: `domain/ai/services/llm_service.py`
- Test: `tests/unit/domain/ai/value_objects/test_prompt.py`
- Test: `tests/unit/domain/ai/value_objects/test_token_usage.py`

- [ ] **Step 1: 创建 AI 领域包结构**

```bash
mkdir -p domain/ai/value_objects
mkdir -p domain/ai/services
touch domain/ai/__init__.py
touch domain/ai/value_objects/__init__.py
touch domain/ai/services/__init__.py
mkdir -p tests/unit/domain/ai/value_objects
touch tests/unit/domain/ai/__init__.py
touch tests/unit/domain/ai/value_objects/__init__.py
```

- [ ] **Step 2: 编写 Prompt 值对象测试**

```python
# tests/unit/domain/ai/value_objects/test_prompt.py
import pytest
from domain.ai.value_objects.prompt import Prompt


def test_prompt_creation():
    """测试创建 Prompt"""
    prompt = Prompt(
        system="你是一个小说创作助手",
        user="请帮我写一个开头"
    )
    assert prompt.system == "你是一个小说创作助手"
    assert prompt.user == "请帮我写一个开头"


def test_prompt_empty_user_raises_error():
    """测试空用户消息抛出异常"""
    with pytest.raises(ValueError):
        Prompt(system="系统消息", user="")


def test_prompt_to_messages():
    """测试转换为消息列表"""
    prompt = Prompt(
        system="系统消息",
        user="用户消息"
    )
    messages = prompt.to_messages()

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "系统消息"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "用户消息"
```

- [ ] **Step 3: 运行测试验证失败**

Run: `pytest tests/unit/domain/ai/value_objects/test_prompt.py -v`
Expected: FAIL

- [ ] **Step 4: 实现 Prompt 值对象**

```python
# domain/ai/value_objects/prompt.py
from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass(frozen=True)
class Prompt:
    """提示词值对象"""
    system: str
    user: str

    def __post_init__(self):
        if not self.user or not self.user.strip():
            raise ValueError("User message cannot be empty")

    def to_messages(self) -> List[Dict[str, Any]]:
        """转换为消息列表格式"""
        messages = []
        if self.system:
            messages.append({"role": "system", "content": self.system})
        messages.append({"role": "user", "content": self.user})
        return messages
```

- [ ] **Step 5: 运行测试验证通过**

Run: `pytest tests/unit/domain/ai/value_objects/test_prompt.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: 编写 TokenUsage 值对象测试**

```python
# tests/unit/domain/ai/value_objects/test_token_usage.py
import pytest
from domain.ai.value_objects.token_usage import TokenUsage


def test_token_usage_creation():
    """测试创建 TokenUsage"""
    usage = TokenUsage(input_tokens=100, output_tokens=200)
    assert usage.input_tokens == 100
    assert usage.output_tokens == 200
    assert usage.total_tokens == 300


def test_token_usage_negative_raises_error():
    """测试负数 token 抛出异常"""
    with pytest.raises(ValueError):
        TokenUsage(input_tokens=-10, output_tokens=100)


def test_token_usage_addition():
    """测试 TokenUsage 相加"""
    usage1 = TokenUsage(input_tokens=100, output_tokens=200)
    usage2 = TokenUsage(input_tokens=50, output_tokens=150)

    total = usage1 + usage2

    assert total.input_tokens == 150
    assert total.output_tokens == 350
    assert total.total_tokens == 500
```

- [ ] **Step 7: 运行测试验证失败**

Run: `pytest tests/unit/domain/ai/value_objects/test_token_usage.py -v`
Expected: FAIL

- [ ] **Step 8: 实现 TokenUsage 值对象**

```python
# domain/ai/value_objects/token_usage.py
from dataclasses import dataclass


@dataclass(frozen=True)
class TokenUsage:
    """Token 使用量值对象"""
    input_tokens: int
    output_tokens: int

    def __post_init__(self):
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError("Token counts cannot be negative")

    @property
    def total_tokens(self) -> int:
        """总 token 数"""
        return self.input_tokens + self.output_tokens

    def __add__(self, other: 'TokenUsage') -> 'TokenUsage':
        """相加两个 TokenUsage"""
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens
        )
```

- [ ] **Step 9: 运行测试验证通过**

Run: `pytest tests/unit/domain/ai/value_objects/test_token_usage.py -v`
Expected: PASS (3 tests)

- [ ] **Step 10: 实现 LLMService 接口**

```python
# domain/ai/services/llm_service.py
from abc import ABC, abstractmethod
from typing import AsyncIterator
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage


class GenerationConfig:
    """生成配置"""
    def __init__(
        self,
        model: str = "claude-3-5-sonnet-20241022",
        max_tokens: int = 4096,
        temperature: float = 1.0
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature


class GenerationResult:
    """生成结果"""
    def __init__(self, content: str, token_usage: TokenUsage):
        self.content = content
        self.token_usage = token_usage


class LLMService(ABC):
    """LLM 服务接口（领域服务）"""

    @abstractmethod
    async def generate(
        self,
        prompt: Prompt,
        config: GenerationConfig
    ) -> GenerationResult:
        """生成内容"""
        pass

    @abstractmethod
    async def stream_generate(
        self,
        prompt: Prompt,
        config: GenerationConfig
    ) -> AsyncIterator[str]:
        """流式生成内容"""
        pass
```

- [ ] **Step 11: 提交**

```bash
git add domain/ai/ tests/unit/domain/ai/
git commit -m "feat(domain): add AI domain foundation

- Prompt value object with system/user messages
- TokenUsage value object with addition operation
- LLMService interface for generation
- GenerationConfig and GenerationResult DTOs"
```

---

### Task 8: 实现 LLM 提供商基础设施

**Files:**
- Create: `infrastructure/ai/__init__.py`
- Create: `infrastructure/ai/providers/__init__.py`
- Create: `infrastructure/ai/providers/base_provider.py`
- Create: `infrastructure/ai/providers/anthropic_provider.py`
- Create: `infrastructure/config/__init__.py`
- Create: `infrastructure/config/settings.py`
- Test: `tests/unit/infrastructure/ai/providers/test_anthropic_provider.py`

- [ ] **Step 1: 创建 AI 基础设施包结构**

```bash
mkdir -p infrastructure/ai/providers
mkdir -p infrastructure/config
touch infrastructure/ai/__init__.py
touch infrastructure/ai/providers/__init__.py
touch infrastructure/config/__init__.py
mkdir -p tests/unit/infrastructure/ai/providers
touch tests/unit/infrastructure/ai/__init__.py
touch tests/unit/infrastructure/ai/providers/__init__.py
```

- [ ] **Step 2: 实现配置管理**

```python
# infrastructure/config/settings.py
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """应用配置"""

    # LLM 配置
    anthropic_api_key: Optional[str] = None
    ark_api_key: Optional[str] = None
    default_model: str = "claude-3-5-sonnet-20241022"
    default_max_tokens: int = 4096
    default_temperature: float = 1.0

    # 存储配置
    storage_base_path: str = "./output"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# 全局配置实例
settings = Settings()
```

- [ ] **Step 3: 实现 BaseProvider 抽象类**

```python
# infrastructure/ai/providers/base_provider.py
from abc import ABC, abstractmethod
from typing import AsyncIterator
from domain.ai.services.llm_service import (
    LLMService,
    GenerationConfig,
    GenerationResult
)
from domain.ai.value_objects.prompt import Prompt


class BaseProvider(LLMService, ABC):
    """LLM 提供商基类"""

    def __init__(self, api_key: str):
        self.api_key = api_key

    @abstractmethod
    async def generate(
        self,
        prompt: Prompt,
        config: GenerationConfig
    ) -> GenerationResult:
        """生成内容"""
        pass

    @abstractmethod
    async def stream_generate(
        self,
        prompt: Prompt,
        config: GenerationConfig
    ) -> AsyncIterator[str]:
        """流式生成内容"""
        pass
```

- [ ] **Step 4: 编写 AnthropicProvider 测试（使用 mock）**

```python
# tests/unit/infrastructure/ai/providers/test_anthropic_provider.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage
from domain.ai.services.llm_service import GenerationConfig
from infrastructure.ai.providers.anthropic_provider import AnthropicProvider


@pytest.fixture
def provider():
    """提供商实例"""
    return AnthropicProvider(api_key="test-key")


@pytest.mark.asyncio
async def test_generate_success(provider):
    """测试生成成功"""
    prompt = Prompt(system="系统消息", user="用户消息")
    config = GenerationConfig()

    # Mock Anthropic client
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="生成的内容")]
    mock_response.usage = MagicMock(
        input_tokens=10,
        output_tokens=20
    )

    with patch.object(provider, '_client') as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        result = await provider.generate(prompt, config)

        assert result.content == "生成的内容"
        assert result.token_usage.input_tokens == 10
        assert result.token_usage.output_tokens == 20


@pytest.mark.asyncio
async def test_stream_generate(provider):
    """测试流式生成"""
    prompt = Prompt(system="系统消息", user="用户消息")
    config = GenerationConfig()

    # Mock stream response
    async def mock_stream():
        chunks = ["chunk1", "chunk2", "chunk3"]
        for chunk in chunks:
            mock_event = MagicMock()
            mock_event.type = "content_block_delta"
            mock_event.delta = MagicMock(text=chunk)
            yield mock_event

    with patch.object(provider, '_client') as mock_client:
        mock_client.messages.stream = MagicMock(return_value=mock_stream())

        chunks = []
        async for chunk in provider.stream_generate(prompt, config):
            chunks.append(chunk)

        assert chunks == ["chunk1", "chunk2", "chunk3"]
```

- [ ] **Step 5: 运行测试验证失败**

Run: `pytest tests/unit/infrastructure/ai/providers/test_anthropic_provider.py -v`
Expected: FAIL

- [ ] **Step 6: 实现 AnthropicProvider**

```python
# infrastructure/ai/providers/anthropic_provider.py
from typing import AsyncIterator
import anthropic
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage
from domain.ai.services.llm_service import GenerationConfig, GenerationResult
from infrastructure.ai.providers.base_provider import BaseProvider


class AnthropicProvider(BaseProvider):
    """Anthropic Claude 提供商"""

    def __init__(self, api_key: str):
        super().__init__(api_key)
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def generate(
        self,
        prompt: Prompt,
        config: GenerationConfig
    ) -> GenerationResult:
        """生成内容"""
        messages = prompt.to_messages()

        # 提取 system 消息
        system_message = None
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                user_messages.append(msg)

        response = await self._client.messages.create(
            model=config.model,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            system=system_message,
            messages=user_messages
        )

        content = response.content[0].text
        token_usage = TokenUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens
        )

        return GenerationResult(content=content, token_usage=token_usage)

    async def stream_generate(
        self,
        prompt: Prompt,
        config: GenerationConfig
    ) -> AsyncIterator[str]:
        """流式生成内容"""
        messages = prompt.to_messages()

        # 提取 system 消息
        system_message = None
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                user_messages.append(msg)

        async with self._client.messages.stream(
            model=config.model,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            system=system_message,
            messages=user_messages
        ) as stream:
            async for event in stream:
                if event.type == "content_block_delta":
                    yield event.delta.text
```

- [ ] **Step 7: 运行测试验证通过**

Run: `pytest tests/unit/infrastructure/ai/providers/test_anthropic_provider.py -v`
Expected: PASS (2 tests)

- [ ] **Step 8: 提交**

```bash
git add infrastructure/ai/ infrastructure/config/ tests/unit/infrastructure/ai/
git commit -m "feat(infrastructure): add LLM provider infrastructure

- Settings: configuration management with pydantic-settings
- BaseProvider: abstract base class for LLM providers
- AnthropicProvider: Anthropic Claude implementation
- Unit tests with mocked API calls"
```

---

### Task 9: 实现应用层服务基础

**Files:**
- Create: `application/__init__.py`
- Create: `application/dto/__init__.py`
- Create: `application/dto/novel_dto.py`
- Create: `application/services/__init__.py`
- Create: `application/services/novel_service.py`
- Test: `tests/unit/application/services/test_novel_service.py`

- [ ] **Step 1: 创建应用层包结构**

```bash
mkdir -p application/dto
mkdir -p application/services
touch application/__init__.py
touch application/dto/__init__.py
touch application/services/__init__.py
mkdir -p tests/unit/application/services
touch tests/unit/application/__init__.py
touch tests/unit/application/services/__init__.py
```

- [ ] **Step 2: 实现 NovelDTO**

```python
# application/dto/novel_dto.py
from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class CreateNovelDTO:
    """创建小说 DTO"""
    title: str
    author: str
    target_chapters: int


@dataclass
class NovelDTO:
    """小说 DTO"""
    id: str
    title: str
    author: str
    target_chapters: int
    completed_chapters: int
    stage: str
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def from_entity(novel) -> 'NovelDTO':
        """从实体创建 DTO"""
        return NovelDTO(
            id=novel.novel_id.value,
            title=novel.title,
            author=novel.author,
            target_chapters=novel.target_chapters,
            completed_chapters=novel.completed_chapters,
            stage=novel.stage.value,
            created_at=novel.created_at,
            updated_at=novel.updated_at
        )
```

- [ ] **Step 3: 编写 NovelService 测试**

```python
# tests/unit/application/services/test_novel_service.py
import pytest
from unittest.mock import Mock
from domain.novel.entities.novel import Novel, NovelStage
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.repositories.novel_repository import NovelRepository
from application.services.novel_service import NovelService
from application.dto.novel_dto import CreateNovelDTO
from domain.shared.exceptions import EntityNotFoundError


@pytest.fixture
def mock_repository():
    """Mock 仓储"""
    return Mock(spec=NovelRepository)


@pytest.fixture
def service(mock_repository):
    """服务实例"""
    return NovelService(repository=mock_repository)


def test_create_novel(service, mock_repository):
    """测试创建小说"""
    dto = CreateNovelDTO(
        title="测试小说",
        author="测试作者",
        target_chapters=10
    )

    result = service.create_novel(dto)

    assert result.title == "测试小说"
    assert result.author == "测试作者"
    assert mock_repository.save.called


def test_get_novel_success(service, mock_repository):
    """测试获取小说成功"""
    novel = Novel(
        id=NovelId("novel-1"),
        title="测试小说",
        author="测试作者",
        target_chapters=10
    )
    mock_repository.get_by_id.return_value = novel

    result = service.get_novel("novel-1")

    assert result.id == "novel-1"
    assert result.title == "测试小说"


def test_get_novel_not_found(service, mock_repository):
    """测试获取不存在的小说"""
    mock_repository.get_by_id.return_value = None

    with pytest.raises(EntityNotFoundError):
        service.get_novel("nonexistent")


def test_list_novels(service, mock_repository):
    """测试列出所有小说"""
    novels = [
        Novel(
            id=NovelId("novel-1"),
            title="小说1",
            author="作者1",
            target_chapters=10
        ),
        Novel(
            id=NovelId("novel-2"),
            title="小说2",
            author="作者2",
            target_chapters=20
        )
    ]
    mock_repository.list_all.return_value = novels

    result = service.list_novels()

    assert len(result) == 2
    assert result[0].id == "novel-1"
    assert result[1].id == "novel-2"
```

- [ ] **Step 4: 运行测试验证失败**

Run: `pytest tests/unit/application/services/test_novel_service.py -v`
Expected: FAIL

- [ ] **Step 5: 实现 NovelService**

```python
# application/services/novel_service.py
from typing import List
import uuid
from domain.novel.entities.novel import Novel, NovelStage
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.repositories.novel_repository import NovelRepository
from application.dto.novel_dto import CreateNovelDTO, NovelDTO
from domain.shared.exceptions import EntityNotFoundError


class NovelService:
    """小说应用服务"""

    def __init__(self, repository: NovelRepository):
        self.repository = repository

    def create_novel(self, dto: CreateNovelDTO) -> NovelDTO:
        """创建小说"""
        novel_id = NovelId(f"novel-{uuid.uuid4().hex[:8]}")

        novel = Novel(
            id=novel_id,
            title=dto.title,
            author=dto.author,
            target_chapters=dto.target_chapters,
            stage=NovelStage.PLANNING
        )

        self.repository.save(novel)

        return NovelDTO.from_entity(novel)

    def get_novel(self, novel_id: str) -> NovelDTO:
        """获取小说"""
        novel = self.repository.get_by_id(NovelId(novel_id))
        if novel is None:
            raise EntityNotFoundError("Novel", novel_id)

        return NovelDTO.from_entity(novel)

    def list_novels(self) -> List[NovelDTO]:
        """列出所有小说"""
        novels = self.repository.list_all()
        return [NovelDTO.from_entity(novel) for novel in novels]

    def delete_novel(self, novel_id: str) -> None:
        """删除小说"""
        if not self.repository.exists(NovelId(novel_id)):
            raise EntityNotFoundError("Novel", novel_id)

        self.repository.delete(NovelId(novel_id))
```

- [ ] **Step 6: 运行测试验证通过**

Run: `pytest tests/unit/application/services/test_novel_service.py -v`
Expected: PASS (4 tests)

- [ ] **Step 7: 提交**

```bash
git add application/ tests/unit/application/
git commit -m "feat(application): add Novel application service

- CreateNovelDTO and NovelDTO for data transfer
- NovelService: create, get, list, delete operations
- Unit tests with mocked repository"
```

---

### Task 10: Week 1 集成测试和文档

**Files:**
- Create: `tests/integration/test_novel_workflow.py`
- Create: `docs/architecture/week1-summary.md`

- [ ] **Step 1: 编写端到端集成测试**

```python
# tests/integration/test_novel_workflow.py
import pytest
import tempfile
import shutil
from domain.novel.value_objects.novel_id import NovelId
from infrastructure.persistence.storage.file_storage import FileStorage
from infrastructure.persistence.repositories.file_novel_repository import FileNovelRepository
from application.services.novel_service import NovelService
from application.dto.novel_dto import CreateNovelDTO


@pytest.fixture
def temp_dir():
    """临时目录"""
    temp_path = tempfile.mkdtemp()
    yield temp_path
    shutil.rmtree(temp_path)


@pytest.fixture
def novel_service(temp_dir):
    """完整的服务栈"""
    storage = FileStorage(base_path=temp_dir)
    repository = FileNovelRepository(storage=storage)
    return NovelService(repository=repository)


def test_complete_novel_workflow(novel_service):
    """测试完整的小说工作流"""
    # 1. 创建小说
    create_dto = CreateNovelDTO(
        title="集成测试小说",
        author="测试作者",
        target_chapters=5
    )
    created = novel_service.create_novel(create_dto)
    assert created.title == "集成测试小说"
    novel_id = created.id

    # 2. 获取小说
    retrieved = novel_service.get_novel(novel_id)
    assert retrieved.id == novel_id
    assert retrieved.title == "集成测试小说"

    # 3. 列出所有小说
    novels = novel_service.list_novels()
    assert len(novels) == 1
    assert novels[0].id == novel_id

    # 4. 删除小说
    novel_service.delete_novel(novel_id)

    # 5. 验证已删除
    from domain.shared.exceptions import EntityNotFoundError
    with pytest.raises(EntityNotFoundError):
        novel_service.get_novel(novel_id)
```

- [ ] **Step 2: 运行集成测试**

Run: `pytest tests/integration/test_novel_workflow.py -v`
Expected: PASS (1 test)

- [ ] **Step 3: 运行所有测试验证覆盖率**

Run: `pytest --cov=domain --cov=application --cov=infrastructure --cov-report=term-missing`
Expected: Coverage > 80%

- [ ] **Step 4: 创建 Week 1 总结文档**

```markdown
# Week 1 实施总结

## 完成内容

### 领域层 (Domain)
- ✅ 基础设施：BaseEntity, DomainException, DomainEvent
- ✅ Novel 聚合根：Novel, Chapter 实体
- ✅ Novel 值对象：NovelId, WordCount, ChapterContent
- ✅ AI 值对象：Prompt, TokenUsage
- ✅ 仓储接口：NovelRepository, ChapterRepository
- ✅ LLM 服务接口：LLMService

### 基础设施层 (Infrastructure)
- ✅ 存储抽象：StorageBackend 接口, FileStorage 实现
- ✅ 仓储实现：FileNovelRepository
- ✅ 数据映射：NovelMapper
- ✅ LLM 提供商：BaseProvider, AnthropicProvider
- ✅ 配置管理：Settings

### 应用层 (Application)
- ✅ DTO：CreateNovelDTO, NovelDTO
- ✅ 应用服务：NovelService

### 测试
- ✅ 单元测试：领域层、应用层、基础设施层
- ✅ 集成测试：文件存储、仓储、完整工作流
- ✅ 测试覆盖率：> 80%

## 目录结构

```
domain/
├── shared/          # 共享内核
├── novel/           # 小说聚合
└── ai/              # AI 领域

application/
├── dto/             # 数据传输对象
└── services/        # 应用服务

infrastructure/
├── persistence/     # 持久化
│   ├── storage/     # 存储抽象
│   ├── repositories/# 仓储实现
│   └── mappers/     # 数据映射
├── ai/              # AI 基础设施
│   └── providers/   # LLM 提供商
└── config/          # 配置管理
```

## 验收标准

- [x] DDD 分层结构完整
- [x] 领域模型实现完成
- [x] 基础设施层实现完成
- [x] 单元测试覆盖率 > 80%
- [x] 集成测试通过
- [x] 所有测试通过

## 下一步 (Week 2)

1. 实现接口层 (interfaces/api/v1/)
2. 迁移现有路由到新架构
3. 实现 LLM 客户端完整功能
4. 前端类型定义和 API 客户端

## 技术债务

- Bible 聚合根尚未实现（Week 2）
- GenerationTask 实体尚未实现（Week 2）
- ARK 提供商尚未实现（Week 2）
- Chapter 仓储实现尚未完成（Week 2）
```

- [ ] **Step 5: 保存文档**

```bash
mkdir -p docs/architecture
cat > docs/architecture/week1-summary.md << 'EOF'
[上面的文档内容]
EOF
```

- [ ] **Step 6: 最终提交**

```bash
git add tests/integration/ docs/architecture/
git commit -m "test: add Week 1 integration tests and summary

- End-to-end workflow test: create, get, list, delete
- Coverage report: > 80% for domain, application, infrastructure
- Week 1 summary document with completion checklist"
```

---

## Week 1 完成检查清单

### 领域层
- [ ] Task 1: 领域层基础结构（BaseEntity, 异常, 事件）
- [ ] Task 2: Novel 值对象（NovelId, WordCount, ChapterContent）
- [ ] Task 3: Novel 实体和聚合根（Novel, Chapter）
- [ ] Task 4: 仓储接口（NovelRepository, ChapterRepository）
- [ ] Task 7: AI 领域基础（Prompt, TokenUsage, LLMService）

### 基础设施层
- [ ] Task 5: 存储抽象层（StorageBackend, FileStorage）
- [ ] Task 6: Novel 仓储实现（FileNovelRepository, NovelMapper）
- [ ] Task 8: LLM 提供商基础设施（AnthropicProvider, Settings）

### 应用层
- [ ] Task 9: 应用层服务基础（NovelService, DTOs）

### 测试和文档
- [ ] Task 10: 集成测试和文档（端到端测试, Week 1 总结）

### 验收标准
- [ ] 所有单元测试通过
- [ ] 所有集成测试通过
- [ ] 测试覆盖率 > 80%
- [ ] 代码已提交到 Git
- [ ] 文档已更新

---

## 执行说明

**推荐执行方式：**

使用 `superpowers:subagent-driven-development` 技能执行本计划：
- 每个 Task 由独立的 subagent 执行
- 每个 Task 完成后进行两阶段审查（规格合规 + 代码质量）
- 快速迭代，高质量输出

**替代方式：**

使用 `superpowers:executing-plans` 技能批量执行：
- 在当前会话中顺序执行
- 在检查点处暂停审查

---

**Week 1 计划完成。Week 2 和 Week 3 计划将在 Week 1 验收后创建。**
