from hachoir_parser import HachoirParser
from hachoir_core.field import FieldSet, RootSeekableFieldSet, RawBytes
from hachoir_core.endian import LITTLE_ENDIAN
from hachoir_core.stream import StringInputStream
from hachoir_parser.misc.msoffice_summary import Summary, CompObj

PROPERTY_NAME = {
    u"\5DocumentSummaryInformation": "doc_summary",
    u"\5SummaryInformation": "summary",
}

class ParseFragments(HachoirParser, RootSeekableFieldSet):
    tags = {
        "description": "Microsoft Office document subfragments",
    }
    endian = LITTLE_ENDIAN

    def __init__(self, stream, **args):
        RootSeekableFieldSet.__init__(self, None, "root", stream, None, stream.askSize(self))
        HachoirParser.__init__(self, stream, **args)

    def validate(self):
        return True

    def createFields(self):
        for index, property in enumerate(self.ole2.properties):
            if index == 0:
                continue
            try:
                name = PROPERTY_NAME[property["name"].value]
            except LookupError:
                name = property.name+"content"
            for field in self.parseProperty(index, property, name):
                yield field

    def parseProperty(self, property_index, property, name_prefix):
        ole2 = self.ole2
        if not property["size"].value:
            return
        if property["size"].value >= ole2["header/threshold"].value:
            return
        name = "%s[]" % name_prefix
        first = None
        previous = None
        size = 0
        start = property["start"].value
        chain = ole2.getChain(start, ole2.ss_fat)
        blocksize = ole2.ss_size
        seek = ole2.seekSBlock
        desc_format = "Small blocks %s..%s (%s)"
        fragment_group = None
        while True:
            try:
                block = chain.next()
                contigious = False
                if not first:
                    first = block
                    contigious = True
                if previous and block == (previous+1):
                    contigious = True
                if contigious:
                    previous = block
                    size += blocksize
                    continue
            except StopIteration:
                block = None
            seek(first)
            desc = desc_format % (first, previous, previous-first+1)
            if name_prefix in ("summary", "doc_summary"):
                yield Summary(self, name, desc, size=size)
            elif property_index == 1:
                yield CompObj(self, "comp_obj", desc, size=size)
            else:
                yield RawBytes(self, name, size//8, desc)
            if block is None:
                break
            first = block
            previous = block
            size = ole2.sector_size

class FragmentGroup:
    def __init__(self):
        self.items = []

    def add(self, item):
        self.items.append(item)

    def createInputStream(self):
        # FIXME: Use lazy stream creation
        data = []
        for item in self.items:
            data.append( item["rawdata"].value )
        data = "".join(data)

        # FIXME: Use smarter code to send arguments
        args = {"ole2": self.items[0].root}
        tags = {"class": ParseFragments, "args": args}
        tags = tags.iteritems()
        return StringInputStream(data, "<fragment group>", tags=tags)

class CustomFragment(FieldSet):
    def __init__(self, parent, name, size, description=None, group=None):
        FieldSet.__init__(self, parent, name, description, size=size)
        if not group:
            group = FragmentGroup()
        self.group = group
        self.group.add(self)

    def createFields(self):
        yield RawBytes(self, "rawdata", self.size//8)

    def _createInputStream(self, **args):
        return self.group.createInputStream()
