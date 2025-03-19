import ipaddress as ipaddr
import sys
import re
import logging

"Functions to match according to a requirement specification."
try:
    _HAS_IPADDR = True
except ImportError:
    _HAS_IPADDR = False
LOG = logging.getLogger("hardware.matcher")


def _adder(array, index, value):
    """Auxiliary function to add a value to an array."""
    array[index] = value


def _appender(array, index, value):
    """Auxiliary function to append a value to an array."""
    try:
        array[index].append(value)
    except KeyError:
        array[index] = [value]


def _range(elt, minval, maxval):
    """Helper for match_spec."""
    return float(elt) >= float(minval) and float(elt) <= float(maxval)


def _gt(left, right):
    """Helper for match_spec."""
    return float(left) > float(right)


def _ge(left, right):
    """Helper for match_spec."""
    return float(left) >= float(right)


def _lt(left, right):
    """Helper for match_spec."""
    return float(left) < float(right)


def _le(left, right):
    """Helper for match_spec."""
    return float(left) <= float(right)


def _not(_, right):
    """Helper for match_spec."""
    return not right


def _and(_, left, right):
    """Helper for match_spec."""
    return left and right


def _or(_, left, right):
    """Helper for match_spec."""
    return left or right


def _network(left, right):
    """Helper for match_spec."""
    if _HAS_IPADDR:
        return ipaddr.IPv4Address(left) in ipaddr.IPv4Network(right)
    else:
        return False


def _regexp(left, right):
    """Helper for match_spec."""
    return re.search(right, left) is not None


def _in(elt, *lst):
    """Helper for match_spec."""
    return elt in lst


_FUNC_REGEXP = re.compile("^([^(]+)\\(\\s*([^,]+)(?:\\s*,\\s*(.+))?\\)$")


def _call_func(func, implicit, res):
    """Helper function for extract_result and match_spec"""
    args = [implicit, res.group(2)]
    if res.group(3):
        args = args + re.split("\\s*,\\s*", res.group(3))
    args = [x.strip("'\"") for x in args]
    args = [_extract_result(implicit, x) for x in args]
    return func(*args)


def _extract_result(implicit, expr):
    """Helper function for match_spec"""
    res = _FUNC_REGEXP.search(expr)
    if res:
        func_name = "_" + res.group(1)
        if func_name in globals():
            return _call_func(globals()[func_name], implicit, res)
        else:
            return expr
    else:
        return expr


def match_spec(spec, lines, arr, adder=_adder):
    """Match a line according to a spec and store variables in <var>."""
    for idx in range(len(lines)):
        if lines[idx] == spec:
            res = lines[idx]
            del lines[idx]
            return res
    for lidx in range(len(lines)):
        line = lines[lidx]
        varidx = []
        for idx in range(4):
            if spec[idx][0] == "$":
                parts = spec[idx].split("=")
                if len(parts) == 2:
                    (var, func) = parts
                    matched = False
                else:
                    var = func = spec[idx]
            else:
                var = func = spec[idx]
            if func[-1] == ")":
                res = _FUNC_REGEXP.search(func)
                if res:
                    func_name = "_" + res.group(1)
                    if func_name in globals():
                        if not _call_func(globals()[func_name], line[idx], res):
                            if var == func:
                                break
                        else:
                            if var == func:
                                continue
                            matched = True
                    elif var == func:
                        break
            if (var == func or (var != func and matched)) and var[0] == "$":
                if adder == _adder and var[1:] in arr:
                    if arr[var[1:]] != line[idx]:
                        break
                varidx.append((idx, var[1:]))
            elif line[idx] != spec[idx]:
                break
        else:
            for i, var in varidx:
                adder(arr, var, line[i])
            res = lines[lidx]
            del lines[lidx]
            return res
    return False


def match_all(lines, specs, arr, arr2, debug=False, level=0):
    """Match all lines according to a spec.

    Store variables starting with a $ in <arr>. Variables starting with
    2 $ like $$vda are stored in arr and arr2.
    """
    lines = list(lines)
    specs = list(specs)
    copy_arr = dict(arr)
    points = []
    if level == 50:
        return False
    while len(specs) > 0:
        copy_specs = list(specs)
        spec = specs.pop(0)
        line = match_spec(spec, lines, arr)
        if debug:
            sys.stderr.write("match_spec: %s %s\n" % (line, spec))
        if not line:
            while len(points) > 0:
                (lines, specs, new_arr) = points.pop()
                if debug:
                    sys.stderr.write("retrying with: %s\n" % (new_arr,))
                if match_all(lines, specs, new_arr, arr2, debug, level + 1):
                    for k in new_arr:
                        arr[k] = new_arr[k]
                    if debug:
                        sys.stderr.write("success: %d\n" % level)
                    return True
            if level == 0 and debug:
                sys.stderr.write("spec: %s not matched\n" % str(spec))
            return False
        elif arr != copy_arr:
            copy_lines = list(lines)
            copy_lines.append(line)
            points.append((copy_lines, copy_specs, copy_arr))
            copy_arr = dict(arr)
            if debug:
                sys.stderr.write("new var: %s %s\n" % (arr, line))
    for key in arr:
        if key[0] == "$":
            nkey = key[1:]
            arr[nkey] = arr[key]
            arr2[nkey] = arr[key]
            del arr[key]
    return True


def match_multiple(lines, spec, arr):
    """Use spec to find all the matching lines and gather variables."""
    ret = False
    lines = list(lines)
    while match_spec(spec, lines, arr, adder=_appender):
        ret = True
    return ret


def generate_filename_and_macs(items):
    """Generate a file name for a hardware using DMI information.

    (product name and version) then if the DMI serial number is
    available we use it unless we lookup the first mac address.
    As a result, we do have a filename like :

    <dmi_product_name>-<dmi_product_version>-{dmi_serial_num|mac_address}
    """
    hw_items = list(items)
    sysvars = {}
    sysvars["sysname"] = ""
    if match_spec(("system", "product", "vendor", "$sysprodvendor"), hw_items, sysvars):
        sysvars["sysname"] += re.sub("\\W+", "", sysvars["sysprodvendor"]) + "-"
    if match_spec(("system", "product", "name", "$sysprodname"), hw_items, sysvars):
        sysvars["sysname"] = re.sub("\\W+", "", sysvars["sysprodname"]) + "-"
    if match_spec(("system", "product", "serial", "$sysserial"), hw_items, sysvars):
        sysvars["sysname"] += re.sub("\\W+", "", sysvars["sysserial"]) + "-"
    if match_multiple(hw_items, ("network", "$eth", "serial", "$serial"), sysvars):
        sysvars["sysname"] += sysvars["serial"][0].replace(":", "-")
    else:
        LOG.warning("unable to detect network macs")
    return sysvars
