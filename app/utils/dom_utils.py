class DomUtils:
    @staticmethod
    def tag_value(tag_item, tag_name, attname="", default=None):
        """
        解析XML标签值
        """
        tag_names = tag_item.getElementsByTagName(tag_name)
        if tag_names:
            if attname:
                attvalue = tag_names[0].getAttribute(attname)
                if attvalue:
                    return attvalue
            else:
                first_child = tag_names[0].firstChild
                if first_child:
                    return first_child.data
        return default

    @staticmethod
    def add_node(doc, parent, name, value=None):
        """
        添加一个DOM节点
        """
        node = doc.createElement(name)
        parent.appendChild(node)
        if value is not None:
            text = doc.createTextNode(str(value))
            node.appendChild(text)
        return node
