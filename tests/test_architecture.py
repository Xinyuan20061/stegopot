"""StegoPot 四层架构边界的静态测试。"""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "stegopot"
EXPECTED_TOP_LEVEL_LAYERS = {
    "application",
    "bootstrap",
    "domain",
    "infrastructure",
}

# 每个逻辑区域只能依赖自身和明确列出的内层区域。
ALLOWED_PROJECT_DEPENDENCIES = {
    "domain": set(),
    "domain.model": {"domain.model"},
    "domain.interface": {"domain.interface", "domain.model"},
    "application": set(),
    "application.engine": {
        "application.engine",
        "domain.interface",
        "domain.model",
    },
    "application.services": {
        "application.engine",
        "application.services",
        "domain.interface",
        "domain.model",
    },
    "infrastructure": set(),
    "infrastructure.settings": {"infrastructure.settings"},
    "infrastructure.llm": {
        "domain.interface",
        "domain.model",
        "infrastructure.llm",
        "infrastructure.settings",
    },
    "infrastructure.substrates": {
        "domain.interface",
        "domain.model",
        "infrastructure.substrates",
    },
    "infrastructure.integrations": {
        "domain.interface",
        "infrastructure.integrations",
    },
    "bootstrap": {
        "application.engine",
        "application.services",
        "bootstrap",
        "domain.interface",
        "domain.model",
        "infrastructure.integrations",
        "infrastructure.llm",
        "infrastructure.settings",
        "infrastructure.substrates",
    },
}


class ArchitectureBoundaryTest(unittest.TestCase):
  """防止低层反向依赖高层或重新产生平级技术包。"""

  def test_only_logical_layers_live_at_package_root(self) -> None:
    """验证包根目录只包含四个逻辑层目录。"""
    actual_layers = {
        path.name
        for path in PACKAGE_ROOT.iterdir()
        if path.is_dir() and path.name != "__pycache__"
    }
    self.assertEqual(actual_layers, EXPECTED_TOP_LEVEL_LAYERS)

  def test_layer_dependencies_follow_declared_direction(self) -> None:
    """验证每个逻辑区域只导入架构允许的区域。"""
    violations: list[str] = []
    for path in PACKAGE_ROOT.rglob("*.py"):
      if "vendor" in path.parts:
        continue
      source_scope = _source_scope(path)
      if source_scope is None:
        continue
      allowed = ALLOWED_PROJECT_DEPENDENCIES[source_scope]
      for dependency in _project_dependencies(path):
        if dependency not in allowed:
          relative_path = path.relative_to(PACKAGE_ROOT.parent)
          violations.append(
              f"{relative_path}: {source_scope} 不允许依赖 {dependency}"
          )
    self.assertEqual(violations, [], "\n".join(violations))

  def test_abstract_contracts_only_live_in_interface_package(self) -> None:
    """验证 ABC 和 Protocol 只存在于 domain/interface。"""
    violations: list[str] = []
    for path in PACKAGE_ROOT.rglob("*.py"):
      if "vendor" in path.parts or _source_scope(path) == "domain.interface":
        continue
      tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
      if _declares_abstract_contract(tree):
        violations.append(str(path.relative_to(PACKAGE_ROOT.parent)))
    self.assertEqual(violations, [], "\n".join(violations))

  def test_flat_or_mixed_packages_are_absent(self) -> None:
    """验证不会重新引入旧的平级包或职责混杂目录。"""
    forbidden_names = {
        "configs",
        "core",
        "integrations",
        "interface",
        "llm",
        "settings",
        "substrates",
        "tools",
        "utils",
        "vendor",
    }
    existing = sorted(
        path.name
        for path in PACKAGE_ROOT.iterdir()
        if path.is_dir() and path.name in forbidden_names
    )
    self.assertEqual(existing, [])


def _source_scope(path: Path) -> str | None:
  """根据源文件路径返回其逻辑区域。

  参数：
    path: 位于 ``stegopot`` 包内的 Python 文件。

  返回：
    例如 ``domain.interface`` 或 ``application.engine``。包根目录的
    ``__init__.py`` 不属于具体逻辑区域，返回 ``None``。
  """
  directory_parts = path.relative_to(PACKAGE_ROOT).parts[:-1]
  for size in (2, 1):
    if len(directory_parts) < size:
      continue
    candidate = ".".join(directory_parts[:size])
    if candidate in ALLOWED_PROJECT_DEPENDENCIES:
      return candidate
  return None


def _project_dependencies(path: Path) -> set[str]:
  """返回文件直接导入的 StegoPot 逻辑区域。

  参数：
    path: 需要分析的 Python 源文件。

  返回：
    例如 ``domain.model`` 或 ``infrastructure.llm`` 的去重集合。
  """
  tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
  dependencies: set[str] = set()
  for node in ast.walk(tree):
    module_names: list[str] = []
    if isinstance(node, ast.ImportFrom) and node.module:
      module_names.append(node.module)
    elif isinstance(node, ast.Import):
      module_names.extend(alias.name for alias in node.names)
    for module_name in module_names:
      dependency = _logical_scope(module_name)
      if dependency is not None:
        dependencies.add(dependency)
  return dependencies


def _logical_scope(module_name: str) -> str | None:
  """把完整模块名归一化为架构测试使用的逻辑区域。"""
  parts = module_name.split(".")
  if len(parts) < 2 or parts[0] != "stegopot":
    return None
  for size in (2, 1):
    candidate = ".".join(parts[1:1 + size])
    if candidate in ALLOWED_PROJECT_DEPENDENCIES:
      return candidate
  return None


def _declares_abstract_contract(tree: ast.AST) -> bool:
  """判断语法树是否声明 ABC、abstractmethod 或 Protocol。"""
  for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef):
      for base in node.bases:
        if _terminal_name(base) in {"ABC", "Protocol"}:
          return True
      for keyword in node.keywords:
        if (
            keyword.arg == "metaclass"
            and _terminal_name(keyword.value) == "ABCMeta"
        ):
          return True
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
      if any(
          _terminal_name(decorator) == "abstractmethod"
          for decorator in node.decorator_list
      ):
        return True
  return False


def _terminal_name(node: ast.AST) -> str | None:
  """返回名称或属性表达式最后一段名称。"""
  if isinstance(node, ast.Name):
    return node.id
  if isinstance(node, ast.Attribute):
    return node.attr
  return None
