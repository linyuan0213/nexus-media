import ipaddress

from app.utils import ExceptionUtils


class SecurityHelper:
    @staticmethod
    def allow_access(allow_ips, ip):
        """
        判断IP是否合法
        :param allow_ips: 充许的IP范围 {"ipv4":, "ipv6":}
        :param ip: 需要检查的ip
        """
        if not allow_ips:
            return True
        try:
            ipaddr = ipaddress.ip_address(ip)
            if ipaddr.version == 4:
                if not allow_ips.get("ipv4"):
                    return True
                allow_ipv4s = allow_ips.get("ipv4").split(",")
                for allow_ipv4 in allow_ipv4s:
                    if ipaddr in ipaddress.ip_network(allow_ipv4):
                        return True
            elif ipaddr.version == 6:
                ipv4_mapped = getattr(ipaddr, "ipv4_mapped", None)
                if ipv4_mapped:
                    if not allow_ips.get("ipv4"):
                        return True
                    allow_ipv4s = allow_ips.get("ipv4").split(",")
                    for allow_ipv4 in allow_ipv4s:
                        if ipv4_mapped in ipaddress.ip_network(allow_ipv4):
                            return True
            else:
                if not allow_ips.get("ipv6"):
                    return True
                allow_ipv6s = allow_ips.get("ipv6").split(",")
                for allow_ipv6 in allow_ipv6s:
                    if ipaddr in ipaddress.ip_network(allow_ipv6):
                        return True
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
        return False
