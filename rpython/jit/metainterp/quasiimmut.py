from rpython.rtyper.lltypesystem import lltype, llmemory
from rpython.rtyper import rclass
from rpython.rtyper.annlowlevel import cast_base_ptr_to_instance
from rpython.jit.metainterp.history import AbstractDescr, ConstPtr, ConstInt,\
     ConstFloat
from rpython.rlib.objectmodel import we_are_translated


def get_mutate_field_name(fieldname):
    if fieldname.startswith('inst_'):    # lltype
        return 'mutate_' + fieldname[5:]
    else:
        raise AssertionError(fieldname)

def get_current_qmut_instance(cpu, gcref, mutatefielddescr):
    """Returns the current QuasiImmut instance in the field,
    possibly creating one.
    """
    qmut_gcref = cpu.bh_getfield_gc_r(gcref, mutatefielddescr)
    if qmut_gcref:
        qmut = QuasiImmut.show(cpu, qmut_gcref)
    else:
        qmut = QuasiImmut(cpu)
        cpu.bh_setfield_gc_r(gcref, qmut.hide(), mutatefielddescr)
    return qmut

def make_invalidation_function(STRUCT, mutatefieldname):
    #
    def _invalidate_now(p):
        qmut_ptr = getattr(p, mutatefieldname)
        setattr(p, mutatefieldname, lltype.nullptr(rclass.OBJECT))
        qmut = cast_base_ptr_to_instance(QuasiImmut, qmut_ptr)
        qmut.invalidate()
    _invalidate_now._dont_inline_ = True
    #
    def invalidation(p):
        if getattr(p, mutatefieldname):
            _invalidate_now(p)
    #
    return invalidation

def do_force_quasi_immutable(cpu, p, mutatefielddescr):
    qmut_ref = cpu.bh_getfield_gc_r(p, mutatefielddescr)
    if qmut_ref:
        cpu.bh_setfield_gc_r(p, cpu.ts.NULLREF, mutatefielddescr)
        qmut_ptr = lltype.cast_opaque_ptr(rclass.OBJECTPTR, qmut_ref)
        qmut = cast_base_ptr_to_instance(QuasiImmut, qmut_ptr)
        qmut.invalidate()


class QuasiImmut(object):
    llopaque = True
    compress_limit = 30

    def __init__(self, cpu):
        self.cpu = cpu
        # list of weakrefs to the LoopTokens that must be invalidated if
        # this value ever changes
        self.looptokens_wrefs = []

    def hide(self):
        qmut_ptr = self.cpu.ts.cast_instance_to_base_ref(self)
        return self.cpu.ts.cast_to_ref(qmut_ptr)

    @staticmethod
    def show(cpu, qmut_gcref):
        qmut_ptr = cpu.ts.cast_to_baseclass(qmut_gcref)
        return cast_base_ptr_to_instance(QuasiImmut, qmut_ptr)

    def register_loop_token(self, wref_looptoken):
        if len(self.looptokens_wrefs) > self.compress_limit:
            self.compress_looptokens_list()
        self.looptokens_wrefs.append(wref_looptoken)

    def compress_looptokens_list(self):
        self.looptokens_wrefs = [wref for wref in self.looptokens_wrefs
                                      if wref() is not None]
        # NB. we must keep around the looptoken_wrefs that are
        # already invalidated; see below
        self.compress_limit = (len(self.looptokens_wrefs) + 15) * 2

    def invalidate(self):
        # When this is called, all the loops that we record become
        # invalid: all GUARD_NOT_INVALIDATED in these loops (and
        # in attached bridges) must now fail.
        wrefs = self.looptokens_wrefs
        self.looptokens_wrefs = []
        for wref in wrefs:
            looptoken = wref()
            if looptoken is not None:
                looptoken.invalidated = True
                self.cpu.invalidate_loop(looptoken)
                # NB. we must call cpu.invalidate_loop() even if
                # looptoken.invalidated was already set to True.
                # It's possible to invalidate several times the
                # same looptoken; see comments in jit.backend.model
                # in invalidate_loop().
                if not we_are_translated():
                    self.cpu.stats.invalidated_token_numbers.add(
                        looptoken.number)


class QuasiImmutDescr(AbstractDescr):
    # those fields are necessary for translation without quasi immutable
    # fields
    struct = lltype.nullptr(llmemory.GCREF.TO)
    fielddescr = None
    
    def __init__(self, cpu, struct, fielddescr, mutatefielddescr):
        self.cpu = cpu
        self.struct = struct
        self.fielddescr = fielddescr
        self.mutatefielddescr = mutatefielddescr
        self.qmut = get_current_qmut_instance(cpu, struct, mutatefielddescr)
        self.constantfieldbox = self.get_current_constant_fieldvalue()

    def get_parent_descr(self):
        if self.fielddescr is not None:
            return self.fielddescr.get_parent_descr()

    def get_index(self):
        if self.fielddescr is not None:
            return self.fielddescr.get_index()
        return 0 # annotation hint

    def get_current_constant_fieldvalue(self):
        struct = self.struct
        fielddescr = self.fielddescr
        if self.fielddescr.is_pointer_field():
            return ConstPtr(self.cpu.bh_getfield_gc_r(struct, fielddescr))
        elif self.fielddescr.is_float_field():
            return ConstFloat(self.cpu.bh_getfield_gc_f(struct, fielddescr))
        else:
            return ConstInt(self.cpu.bh_getfield_gc_i(struct, fielddescr))

    def is_still_valid_for(self, structconst):
        assert self.struct
        if self.struct != structconst.getref_base():
            return False
        cpu = self.cpu
        qmut = get_current_qmut_instance(cpu, self.struct,
                                         self.mutatefielddescr)
        if qmut is not self.qmut:
            return False
        else:
            currentbox = self.get_current_constant_fieldvalue()
            assert self.constantfieldbox.same_constant(currentbox)
            return True
