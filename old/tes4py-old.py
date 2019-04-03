# using construct3 to parse TES4: Oblivion Script files (.esp & .esm)

# general structure:
# see: http://www.uesp.net/wiki/Tes4Mod:Mod_File_Format
#
# a single header record to start.
# followed by a series of groups
# groups can either contain either more groups or records
# (in practice certain groups always have group children and other groups always have records as children)
# accept groups in any order output in a particular order
# Records can be compressed with zlib
# Records, Groups, and Subrecords all have 4 letter ascii names. (though the group name cannot be trusted)
# Groups are kind of structured like records with a record_type of GRUP except not really
# the group with the name ARMO contains only records of type ARMO
# Subrecords will be matched based on record type and subrecord type to a schema.
# many sub-records are atomic values (single strings) but many others are not.

# will need a way to pack/unpack to a cache format that can then be manipulated with something stronger.
# probably sqlalchemy, maybe flatland

# raw API will look like this:
# scriptfile = ScriptFile(filename)
# scriptfile['TES4'][0] # header record
# scriptfile['GRUP'][0]['subrecords']['EDID'][0]['value'] == 'shirt'
# scriptfile['GRUP'][0]['subrecords']['DATA'][0]['gold_value']
# scriptfile['GRUP'][0]['subrecords']['DATA'][0]['weight']
#
# nice API would look something like:
# scriptfile.byEDID('myshirt').gold_value = 20
# scriptfile.save()

from itertools import chain, product, count
from collections import defaultdict
from io import BytesIO, IOBase
import zlib

from construct3 import *
from construct3.adapters import UnnamedPackerMixin, Adapter, ValidationError, Tunnel, Flags
from construct3.packers import Switch, PackerError
from construct3.packers import _contextify
from construct3.lib.config import Config


## TES 4 Binary Schema ##

pad = Padding
ubyte = uint8
byte = sint8
ulong = uint32l
long = sint32l
ushort = uint16l
formid = ulong
formidref = Struct('formid' / formid)

class CoealescingAdapter(Adapter):
	def __init__(self, underlying, typename, keyorder=None):
		super().__init__(underlying)
		#self.keyorder = keyorder
		self.typename = typename
		
	def encode(self, obj, ctx):
		#return self.underlying(chain((obj[key] for key in self.keyorder)))
		self.underlying(chain(obj.values))
		
	def decode(self, objs, ctx):
		r = defaultdict(list)
		for obj in objs:
			r[obj[self.typename]].append(obj)
		return r
		
class Const(Adapter):
	def __init__(self, constval):
		assert isinstance(constval, bytes)
		self.constval = constval
		Adapter.__init__(self, Raw(len(constval)))

	def __repr__(self):
		return "Const(%r)" % (self.constval)

	def encode(self, obj, ctx):
		return self.constval

	def decode(self, obj, ctx):
		if obj != self.constval:
			raise ValidationError("Wrong constant value %r" % (obj,))
		return obj


class ZStringAdapter(Adapter):
	def __init__(self, length):
		super().__init__(Raw(length))

	def encode(self, obj, ctx):
		return obj.encode('windows-1252') + b'\0'

	def decode(self, obj, ctx):
		assert obj[-1] == 0
		return obj[:-1].decode('windows-1252')

char4 = StringAdapter(Raw(4), 'ascii')
zstring = ZStringAdapter(this._.size)

class LazyPacker(Packer):
	# TODO - lots of ways to avoid repeating myself here
	# but most of them would cause some serious performance
	# concerns, methinks
	def __init__(self, packerfn):
		self.packerfn = packerfn
		self.packer = None
		super().__init__()

	def _pack(self, obj, stream, ctx, cfg):
		if self.packer is None:
			self.packer = self.packerfn()

		return self.packer._pack(obj, stream, ctx, cfg)

	def _unpack(self, stream, ctx, cfg):
		if self.packer is None:
			self.packer = self.packerfn()

		return self.packer._unpack(stream, ctx, cfg)

	def _sizeof(self, ctx, cfg):
		if self.packer is None:
			self.packer = self.packerfn()

		return self.packer._sizeof(ctx, cfg)

zstringstruct = Struct( 'value' / zstring)

#list of 3-tuples
#arg0 = set of record types or None for all
#arg2 = set of sub record types
#arg3 = subcrecord schema		
SUBRECORD_SCHEMA = (
	(['*'], ['EDID', 'FULL'], zstringstruct),

	(['TES4'], ['HEDR'], Struct( #REQUIRED
		'version' / float32,
		'num_records' / long,
		'next_object_id' / ulong,
	)),
	(['TES4'], ['OFST'], Range(0, None, Struct(
		'offset' / ubyte[3],
		'type_num' / byte,
		'record_type' / ubyte[4],
	))),
	(['TES4'], ['SNAM', 'CNAM', 'MAST'], zstringstruct),
	(['TES4'], ['DATA'], Struct('fileSize' / Const(b'\0' * 8))),
	#TES4 unhandled: DELE

	(['CLOT', 'ARMO'], ['MODL', 'MOD2', 'MOD3', 'MOD4', 'ICON', 'ICO2', ], zstringstruct),
	(['CLOT', 'ARMO'], ['ENAM'], formidref),
	(['CLOT', 'ARMO'], ['DATA'], Struct(
		'gold_value' / ulong,
		'weight' / float32,
	)),
	(['CLOT', 'ARMO'], 'BMDT', Flags(ulong,
		hide_rings=0x00010000,
		hide_amulet=0x00020000,
		nonplayable=0x00400000,
		default=0xCD000000,
	)),
	# CLOT/ARMO unhandled MODB, MO2B, MO3B, MO4B
	# MODT, MO2T, MO3T, MO4T, MO4T
)

TRANSFORMED_SCHEMA = {}
for record_types, subrecord_types, schema in SUBRECORD_SCHEMA:
	for record_type, subrecord_type in product(record_types, subrecord_types):
		TRANSFORMED_SCHEMA[(record_type, subrecord_type)] = schema

class CustomSwitch(Switch):
	def __init__(self, size):
		self.getsize = _contextify(size)

	def _unpack(self, stream, ctx, cfg):
		size = self.getsize(ctx)
		stream2 = BytesIO(stream.read(size))
		return super()._unpack(stream2, ctx, Config())

	def _choose_packer(self, ctx):
		try:
			return TRANSFORMED_SCHEMA[ctx['_']['_']['record_type'], ctx['subrecord_type']]
		except KeyError:
			pass

		try:
			return TRANSFORMED_SCHEMA['*', ctx['subrecord_type']]
		except KeyError:
			pass

		return Raw(self.getsize(ctx))

class ByteLimitedRange(Packer):
	#__slots__ = ["mincount", "maxcount", "itempkr"]
	def __init__(self, size, itempkr, strict=False):
		self.size = _contextify(size)
		self.itempkr = itempkr
		self.strict = strict

	
	def __repr__(self):
		return "ByteLimitedRange(%r, %r, strict=%r)" % (self.size, self.itempkr, self.strict)
	
	def _pack(self, obj, stream, ctx, cfg):
		ctx2 = {"_" : ctx}
		for i, item in enumerate(obj):
			ctx2[i] = item
			self.itempkr._pack(item, stream, ctx2, cfg)
	
	'''
	def _unpack(self, stream, ctx, cfg):
		size = self.size(ctx)
		stream2 = BytesIO(stream.read(size))
		
		ctx2 = {"_" : ctx}
		
		obj = []
		for i in count():
			try:
				obj2 = self.itempkr._unpack(stream, ctx2, cfg)
				objs.append(obj2)
				ctx2[i] = obj2
			except:
				break
		return obj
	'''
	
	def _unpack(self, stream, ctx, cfg):
		ctx2 = {"_" : ctx}
		obj = []
		startpos = stream.tell()
		bytesconsumed = 0
				
		size = self.size(ctx)
		stream2 = ByteLimitedStream(size, stream)
		
		#import ipdb; ipdb.set_trace()
		for i in count():
			#if stream.tell() - startpos >= size:
			#if bytesconsumed >= self.size:
			#	break
			try:
				obj2 = self.itempkr._unpack(stream2, ctx2, cfg)
				#bytesconsumed += self.itempkr._sizeof(ctx2, cfg)
			
				ctx2[i] = obj2
				obj.append(obj2)
			except PackerError:
				break
			except Exception as ex:
				import pdb; pdb.set_trace()
				break

		
		if self.strict and stream.tell() - startpos != size:
		#if self.strict and byteconsumed != self.size:
			import pdb; pdb.set_trace()
			actual_size = stream.tell() - startpos
			raise Exception('expected to consume %d bytes, actually consumed %d bytes' % (size, actual_size))
		
		#import ipdb; ipdb.set_trace()
		return obj

	def _sizeof(self, ctx, cfg):
		return self.size(ctx)
		
class ByteLimitedStream(IOBase):
	""" wraps a stream, won't let you read past the bytelimit"""
	def __init__(self, bytelimit, stream):
		self.stream = stream
		self.bytelimit = bytelimit
		self.startpos = stream.tell()
	
	def read(self, size=None):
		if not self.bytelimit:
			return b''
		
		bytelimit = self.bytelimit	
		if size is None or size > bytelimit:
			self.bytelimit = 0
			#buf = b''
			
			return self.stream.read()
			#while(len(buf) != bytelimit):
			#	buf = self.stream.read(bytelimit - len(buf))
			#return buf
		else:
			buf = self.stream.read(size)
			self.bytelimit -= len(buf)
			return buf
			
	def tell(self):
		return self.stream.tell() - self.startpos
	
	def seek(self, seekto):
		return self.stream.seek(seekto + self.startpos)
	
	def writeable(self): return False	
	def readable(self): return True
	def seekable(self): return True
	
	
	
		
class MaybeZlibPacker(Packer):
	def __init__(self, is_compressed, phys_size, real_size_packer, underlying):
		"""
		:is_comprseed: contextual to determine if compressed
		:phys_size: contextual of physical size
		:real_size_pkr: packer to unpack "real_size" of compressed data (if compressed)
		
		if not compressed identical to ByteLimitedRange
		"""
		self.is_compressed = _contextify(is_compressed)
		self.phys_size = _contextify(phys_size)
		self.real_size_packer = real_size_packer
		self.underlying = underlying
		
	def _pack(self, obj, stream, ctx, cfg):
		if self.is_compressed(ctx):
			stream2 = BytesIO()
			self.underlying._pack(obj, stream2, ctx, cfg)
			stream.write(zlib.compress(stream2.value()))
		else:
			stream2 = stream
			self.underlying._pack(obj, stream, ctx, cfg)
	
	def _unpack(self, stream, ctx, cfg):
		if self.is_compressed(ctx):
			#import ipdb; ipdb.set_trace()
			size = self.real_size_packer._unpack(stream, ctx, cfg)
			phys_size = self.phys_size(ctx)
			comp_data = stream.read(phys_size - self.real_size_packer._sizeof(ctx, cfg))
			stream2 = BytesIO(zlib.decompress(comp_data))
		else:
			stream2 = ByteLimitedStream(self.phys_size(ctx), stream)
			
		return self.underlying._unpack(stream2, ctx, cfg)
		

# order groups should be written out in
GROUP_ORDER = (
	'GMST', 'GLOB', 'CLAS', 'FACT', 'HAIR', 'EYES', 'RACE', 'SOUN', 'SKIL', 'MGEF',
	'SCPT', 'LTEX', 'ENCH', 'SPEL', 'BSGN', 'ACTI', 'APPA', 'ARMO', 'BOOK', 'CLOT',
	'CONT', 'DOOR', 'INGR', 'LIGH', 'MISC', 'STAT', 'GRAS', 'TREE', 'FLOR', 'FURN',
	'WEAP', 'AMMO', 'NPC_', 'CREA', 'LVLC', 'SLGM', 'KEYM', 'ALCH', 'SBSP', 'SGST',
	'LVLI', 'WTHR', 'CLMT', 'REGN', 'CELL', 'WRLD', 'DIAL', 'QUST', 'IDLE', 'PACK',
	'CSTY', 'LSCR', 'LVSP', 'ANIO', 'WATR', 'EFSH')

class SubStruct(Struct):
	def _unpack(self, stream, ctx, cfg):
		r = super()._unpack(stream, ctx, cfg)
		
		if r['subrecord_type'] == 'GRUP':
			import pdb; pdb.set_trace()
			
		return r
		
SubRecord = SubStruct(
	'subrecord_type' / char4,
	'size' / ushort,
	'vals' / CustomSwitch(this.size),
)

def debug(fn):
	def wrapper(ctx):
		print('##==>', ctx['record_type'])
		return fn(ctx)
	return wrapper


RecordOrGroup = Struct(
	'record_type' / char4,
	'size' / ulong,
	Embedded(If(
		this.record_type == 'GRUP',
		Struct(
			'label' / ubyte[4],
			'groupType' / Enum(
				long,
				top=0,
				world_children=1,
				interior_cell_block=2,
				interior_cell_subblock=3,
				exterior_cell_block=4,
				exterior_cell_subblock=5,
				cell_children=6,
				topic_children=7,
				cell_persistent=8,
				cell_temporary_children=9,
				cell_visible_distant_children=10,
			),
			'stamp' / ulong,
			#'''
			#children' / Tunnel(
			#	Raw(this.size - 20),
			#	Range(0, None, LazyPacker(lambda: RecordOrGroup)),
			#) 
			#'''
			'children' / ByteLimitedRange(
				this.size - 20,
				LazyPacker(lambda: RecordOrGroup),
				strict=True,
			)
			
		),
		Struct(
			'flags' / Flags(ulong,
				isesm=0x01,
				deleted=0x20,
				cast_shadows=0x200,
				quest_item_persistent=0x400,  # means "is quest item" or "is persistent" depending on context
				initially_disabled=0x800,
				ignored=0x1000,
				visible_when_distant=0x8000,
				dangerous_off_limits=0x20000,
				is_compressed=0x40000,
				cant_wait=0x80000,
			),
			'formid' / formid,
			'vc_info' / Struct(
				#version control information
				#mostly useless, too often empty
				#TODO adapter to datetime.date
				'day' / byte,
				'month' / byte,  # 1 = jan, 2003
				'owner' / ushort,
			),
			'subrecords' / MaybeZlibPacker(
				this.flags.is_compressed,
				this.size,
				ulong,
				#CoealescingAdapter(Range(0, None, SubRecord), 'subrecord_type'),
				Range(0, None, SubRecord),
			),
		),
	)),
)

EspEsmFormat = Range(0, None, RecordOrGroup)