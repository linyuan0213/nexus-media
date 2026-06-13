"""DomUtils 单元测试."""

from xml.dom.minidom import Document

from app.utils.dom_utils import DomUtils


class TestDomUtils:
    def test_tag_value_text(self):
        doc = Document()
        root = doc.createElement("root")
        doc.appendChild(root)
        child = doc.createElement("name")
        child.appendChild(doc.createTextNode("value"))
        root.appendChild(child)
        assert DomUtils.tag_value(doc, "name") == "value"

    def test_tag_value_attribute(self):
        doc = Document()
        root = doc.createElement("root")
        doc.appendChild(root)
        child = doc.createElement("item")
        child.setAttribute("id", "123")
        root.appendChild(child)
        assert DomUtils.tag_value(doc, "item", attname="id") == "123"

    def test_tag_value_default(self):
        doc = Document()
        root = doc.createElement("root")
        doc.appendChild(root)
        assert DomUtils.tag_value(doc, "missing", default="fallback") == "fallback"

    def test_tag_value_empty_attribute(self):
        doc = Document()
        root = doc.createElement("root")
        doc.appendChild(root)
        child = doc.createElement("item")
        root.appendChild(child)
        assert DomUtils.tag_value(doc, "item", attname="id", default="x") == "x"

    def test_add_node_without_value(self):
        doc = Document()
        root = doc.createElement("root")
        doc.appendChild(root)
        node = DomUtils.add_node(doc, root, "child")
        assert node.nodeName == "child"
        assert node.firstChild is None

    def test_add_node_with_value(self):
        doc = Document()
        root = doc.createElement("root")
        doc.appendChild(root)
        node = DomUtils.add_node(doc, root, "child", 42)
        assert node.firstChild.data == "42"
