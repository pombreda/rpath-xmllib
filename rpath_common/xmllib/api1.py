#
# Copyright (c) 2008 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.rpath.com/permanent/licenses/CPL-1.0.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#

import StringIO
import os
import subprocess
from xml import sax

simpletypes = (int, long, float, bool, str, unicode, list, set, dict, tuple)

from lxml import etree

def prettyPrint(func):
    def wrapper(*args, **kwargs):
        res = func(*args, **kwargs)
        # XXX: It is fairly inefficient to serialize an
        # ElementTree-like object to XML, then parse it back into an
        # lxml.etree.ElementTree object, then serialize it again just to
        # pretty-print it. Maybe we whould just have _toXml write an
        # ElementTree object to begin with?
        tree = etree.parse(StringIO.StringIO(res))
        res = etree.tostring(tree, pretty_print = True,
            xml_declaration = True, encoding = 'UTF-8')
    return wrapper

class BaseNode(object):
    """
    Base node for all data classes used by SAX handler. Neither this class,
    nor any descendent needs to be instantiated. They should be registered
    with instances of the DataBinder class.

    This class serves as the base datatype. This is the default node type
    if nothing else is specified, thus it's not useful to register this
    class.

    By default, _addChild will add the childNode to a list. specifying an
    attribute in _singleChildren will cause the value to be stored directly.
    """
    _singleChildren = []
    _childOrder = []

    def __init__(self):
        self._text = ''

    def _addChild(self, name, childNode):
        # ensure we don't modify the class attribute
        if id(self._childOrder) == id(self.__class__._childOrder):
            self._childOrder = []
        self._childOrder.append(name)
        if name in self._singleChildren:
            self.__dict__[name] = childNode._finalize()
        else:
            if name not in self.__dict__:
                self.__dict__[name] = []
            self.__dict__[name].append(childNode._finalize())

    def _finalize(self):
        return self

    def _characters(self, ch):
        self._text += ch

class IntegerNode(BaseNode):
    """
    Integer data class for SAX parser.

    Registering a tag with this class will render the text contents into
    an integer when _finalize is called. All attributes and tags will be lost.
    If no text is set, this object will default to 0.
    """
    def _finalize(self):
        return self._text and int(self._text) or 0

class StringNode(BaseNode):
    """
    String data class for SAX parser.

    Registering a tag with this class will render the text contents into
    a string when _finalize is called. All attributes and tags will be lost.
    If no text is set, this object will default to ''.
    """
    def _finalize(self):
        if isinstance(self._text, unicode):
            return self._text
        return str(self._text)

class NullNode(BaseNode):
    """
    Null data class for SAX parser.

    Registering a tag with this class will render the text contents into
    None when _finalize is called. All attributes and tags will be lost.
    All text will be lost.
    """
    def _finalize(self):
        pass

class BooleanNode(BaseNode):
    """
    Boolean data class for SAX parser.

    Registering a tag with this class will render the text contents into
    a bool when _finalize is called. All attributes and tags will be lost.
    '1' or 'true' (case insensitive) will result in True.
    """
    def _finalize(self):
        return self._text.upper().strip() in ('TRUE', '1')

class DictNode(BaseNode):
    """
    Dict container class for SAX parser.

    Registering a tag with this class will return the __dict__  of this class
    when _finalize is called. This effectively means all tags will be
    preserved, but all attributes will be lost.
    """
    def _finalize(self):
        return dict(x for x in self.__dict__.iteritems() \
                if not x[0].startswith('_'))

class BindingHandler(sax.ContentHandler):
    """
    Sax Content handler class.

    This class doesn't need to be instantiated directly. It will be invoked
    on an as-needed basis by DataBinder. This class interfaces with the
    Python builtin SAX parser and creates dynamic python objects based on
    registered node classes. If no nodes are registered, a python object
    structure that looks somewhat like a DOM tree will result.
    """
    def __init__(self, typeDict = None):
        if not typeDict:
            typeDict = {}
        self.typeDict = typeDict
        self.stack = []
        self.rootNode = None
        sax.ContentHandler.__init__(self)

    def registerType(self, key, typeClass):
        self.typeDict[key] = typeClass

    def startElement(self, name, attrs):
        classType = BaseNode
        if name in self.typeDict:
            classType = self.typeDict[name]
        self.stack.append(type(str(name), (classType,), dict(attrs))())

    def endElement(self, name):
        elem = self.stack.pop()
        if not self.stack:
            self.rootNode = elem
        else:
            self.stack[-1]._addChild(name, elem)

    def characters(self, ch):
        elem = self.stack[-1]
        elem._characters(ch)

class DataBinder(object):
    """
    DataBinder class.

    This class wraps all XML parsing logic in this module. As a rough rule
    of thumb, attributes of an XML tag will be treated as class level
    attributes, while subtags will populate an object's main dictionary.

    parseFile: takes a a path and returns a python object.
    parseString: takes a string containing XML data and returns a python
        object.
    registerType: register a tag with a class defining how to treat XML content.
    toXml: takes an object and renders it into an XML representation.

    EXAMPLE:
    class ComplexType(BaseNode):
        _singleChildren = ['foo', 'bar']

    binder = DataBinder()
    binder.registerType('foo', BooleanNode)
    binder.registerType('bar', NullNode)
    binder.registerType('baz', ComplexType)

    obj = binder.parseString('<baz><foo>TRUE</foo><bar>test</bar></baz>')

    obj.foo == True
    obj.bar == 'test'

    EXAMPLE:
    binder = DataBinder()
    class baz(object):
        pass
    obj = baz()
    obj.foo = True
    obj.bar = 'test'
    binder.toXml(obj) == '<baz><foo>true</foo><bar>test</bar></baz>'
    """
    def __init__(self, typeDict = None):
        self.contentHandler = BindingHandler(typeDict)

    def registerType(self, key, val):
        return self.contentHandler.registerType(key, val)

    def parseFile(self, fn):
        f = open(fn)
        data = f.read()
        f.close()
        return self.parseString(data)

    def parseString(self, data):
        self.contentHandler.rootNode = None
        parser = sax.make_parser()
        parser.setContentHandler(self.contentHandler)
        parser.parse(StringIO.StringIO(data))
        rootNode = self.contentHandler.rootNode
        self.contentHandler.rootNode = None
        return rootNode

    def _getChildOrder(self, items, order):
        # sort key is a three part tuple. each element maps to these rules:
        # element one reflects if we know how to order the element.
        # element two reflects the element's position in the ordering.
        # element three sorts everything else by simply providing the original
        # item (aka. default ordering of sort)
        return sorted(items, key = lambda x: \
                (x not in order, x in order and order.index(x), x))

    @staticmethod
    def _etree_add(elem, obj):
        if isinstance(obj, list):
            elem.extend(obj)
        else:
            elem.append(obj)

    def _to_etree_r(self, obj, suggestedName = None):
        name = suggestedName or obj.__class__.__name__

        elem = etree.Element(name)
        if isinstance(obj, bool):
            elem.text = (obj and 'true' or 'false')
        elif isinstance(obj, (int, float, long)):
            elem.text = str(obj)
        elif isinstance(obj, (str, unicode)):
            elem.text = obj
        elif isinstance(obj, (list, set, tuple)):
            elem = [ self._to_etree_r(child, suggestedName) for child in obj]
        elif isinstance(obj, dict):
            for childName, child in sorted(obj.iteritems()):
                self._etree_add(elem, self._to_etree_r(child, suggestedName = childName))
        else:
            attrs = (x for x in obj.__class__.__dict__.iteritems() \
                    if not x[0].startswith('_'))
            attrs = dict((x, self._toString(y)) for x, y in attrs)
            children = dict(x for x in obj.__dict__.iteritems() \
                    if not x[0].startswith('_'))
            elem.attrib.update(attrs)
            ordering = hasattr(obj, '_childOrder') and obj._childOrder or []
            childOrder = self._getChildOrder(children.keys(), ordering)
            for key in childOrder:
                val = children[key]
                self._etree_add(elem, self._to_etree_r(val, key))
            if hasattr(obj, '_text'):
                if obj._text.strip():
                    elem.text = obj._text
        return elem

    @staticmethod
    def _toString(obj):
        if isinstance(obj, (str, unicode)):
            return obj
        return str(obj)

    def toXml(self, obj, suggestedName = None):
        tree = self._to_etree_r(obj, suggestedName)
        res = etree.tostring(tree, pretty_print = True,
            xml_declaration = True, encoding = 'UTF-8')
        return res

    def _toXml(self, obj, suggestedName = None):
        encoding = None
        tree = self._to_etree_r(obj, suggestedName)
        if isinstance(tree, list):
            res = [ etree.tostring(x, pretty_print = False,
                xml_declaration = False, encoding = encoding) for x in tree ]
            res = ''.join(res)
        else:
            res = etree.tostring(tree, pretty_print = False,
                xml_declaration = False, encoding = encoding)
        return res


