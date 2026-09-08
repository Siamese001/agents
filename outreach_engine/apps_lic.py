from _standalone_src_bootstrap import bootstrap_src_package
bootstrap_src_package('apps_lic', globals())

if __name__ == '__main__':
    from apps_lic.__main__ import main
    import sys
    sys.exit(main())
