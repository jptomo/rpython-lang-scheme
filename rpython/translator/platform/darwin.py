"""Support for OS X."""

from rpython.translator.platform import posix

#
# Although Intel 32bit is supported since Apple Mac OS X 10.4, (and PPC since, ever)
# the @rpath handling used in Darwin._args_for_shared is only availabe
# since 10.5, so we use that as minimum requirement.
#
DARWIN_VERSION_MIN = '-mmacosx-version-min=10.5'

class Darwin(posix.BasePosix):
    name = "darwin"

    standalone_only = ('-mdynamic-no-pic',)
    shared_only = ()

    link_flags = (DARWIN_VERSION_MIN,)
    cflags = ('-O3', '-fomit-frame-pointer', DARWIN_VERSION_MIN)

    so_ext = 'dylib'
    DEFAULT_CC = 'clang'
    rpath_flags = ['-Wl,-rpath', '-Wl,@executable_path/']

    def get_rpath_flags(self, rel_libdirs):
        # needed for cross compiling on ARM, needs fixing if relevant for darwin
        if len(rel_libdirs) > 0:
            print 'in get_rpath_flags, rel_libdirs is not fixed up',rel_libdirs
        return self.rpath_flags 

    def _args_for_shared(self, args):
        return (list(self.shared_only)
                + ['-dynamiclib', '-install_name', '@rpath/$(TARGET)', '-undefined', 'dynamic_lookup']
                + args)

    def _include_dirs_for_libffi(self):
        return self._pkg_config("libffi", "--cflags-only-I",
                                ['/usr/include/ffi'],
                                check_result_dir=True)

    def _library_dirs_for_libffi(self):
        return self._pkg_config("libffi", "--libs-only-L",
                                ['/usr/lib'],
                                check_result_dir=True)

    def _frameworks(self, frameworks):
        args = []
        for f in frameworks:
            args.append('-framework')
            args.append(f)
        return args

    def _link_args_from_eci(self, eci, standalone):
        args = super(Darwin, self)._link_args_from_eci(eci, standalone)
        frameworks = self._frameworks(eci.frameworks)
        include_dirs = self._includedirs(eci.include_dirs)
        return (args + frameworks + include_dirs)

    def _exportsymbols_link_flags(self):
        # XXX unsure if OS/X requires an option to the linker to tell
        # "please export all RPY_EXPORTED symbols even in the case of
        # making a binary and not a dynamically-linked library".
        # It's not "-exported_symbols_list" but something close.
        return []

    def gen_makefile(self, cfiles, eci, exe_name=None, path=None,
                     shared=False, headers_to_precompile=[],
                     no_precompile_cfiles = [], icon=None):
        # ensure frameworks are passed in the Makefile
        fs = self._frameworks(eci.frameworks)
        if len(fs) > 0:
            # concat (-framework, FrameworkName) pairs
            self.extra_libs += tuple(map(" ".join, zip(fs[::2], fs[1::2])))
        mk = super(Darwin, self).gen_makefile(cfiles, eci, exe_name, path,
                                shared=shared,
                                headers_to_precompile=headers_to_precompile,
                                no_precompile_cfiles = no_precompile_cfiles,
                                icon=icon)
        return mk

class Darwin_PowerPC(Darwin):#xxx fixme, mwp
    name = "darwin_powerpc"

class Darwin_i386(Darwin):
    name = "darwin_i386"
    DEFAULT_CC = 'clang -arch i386'

class Darwin_x86_64(Darwin):
    name = "darwin_x86_64"
    DEFAULT_CC = 'clang -arch x86_64'
