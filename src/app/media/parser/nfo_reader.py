import defusedxml.ElementTree as ET  # type: ignore[import-untyped]


class NfoReader:
    def __init__(self, xml_file_path):
        self.xml_file_path = xml_file_path
        tree = ET.parse(xml_file_path)
        root = tree.getroot()
        assert root is not None
        self.root = root

    def get_element_value(self, element_path):
        element = self.root.find(element_path)
        return element.text if element is not None else None
