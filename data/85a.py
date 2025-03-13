import logging
import paramiko


logger = logging.getLogger(__name__)


class RemoteConfig(object):
    def __init__(self, device_ref, localpath, remotepath, configfilename):
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.host = device_ref['ip']
        self.user = device_ref['login']
        self.password = device_ref['password']
        self.remotepath = remotepath
        self.configfilename = configfilename
        self.localpath = localpath

    def get_config(self):
        logger.debug('[HAPROXY] get config from remote server %s/%s to %s/%s' %
                      (self.remotepath, self.configfilename,
                       self.localpath, self.configfilename))
        self.ssh.connect(self.host, username=self.user, password=self.password)
        sftp = self.ssh.open_sftp()
        sftp.get('%s/%s' % (self.remotepath, self.configfilename),
                 '%s/%s' % (self.localpath, self.configfilename))
        sftp.close()
        self.ssh.close()

    def put_config(self):
        logger.debug('[HAPROXY] put configuration to remote server')
        self.ssh.connect(self.host, username=self.user, password=self.password)
        sftp = self.ssh.open_sftp()
        sftp.put('%s/%s' % (self.localpath, self.configfilename),
                 '/tmp/%s' % self.configfilename)
        self.ssh.exec_command('sudo mv /tmp/%s %s' %
                               (self.configfilename, self.remotepath))
        sftp.close()
        self.ssh.close()

    def validate_config(self):
        '''
            Validate conifig and restart haproxy
        '''
        self.ssh.connect(self.host, username=self.user, password=self.password)
        stdin, stdout, stderr = self.ssh.exec_command('haproxy -c -f %s/%s' %
                               (self.remotepath, self.configfilename))
        ssh_out = stdout.read()
        if (ssh_out.find('Configuration file is valid')) >= 0:
            logger.debug('[HAPROXY] remote configuration is valid,\
                          restart haproxy')
            self.ssh.exec_command('sudo service haproxy restart')
            return True
        else:
            logger.error('[HAPROXY] remote configuration is not valid')
            return False
        self.ssh.close()


class RemoteService(object):
    '''
    Operations with haproxy daemon
    '''
    def __init__(self, device_ref):
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.host = device_ref['ip']
        self.user = device_ref['login']
        self.password = device_ref['password']

    def start(self):
        self.ssh.connect(self.host, username=self.user, password=self.password)
        self.ssh.exec_command('sudo service haproxy start')
        self.ssh.close()

    def stop(self):
        self.ssh.connect(self.host, username=self.user, password=self.password)
        self.ssh.exec_command('sudo service haproxy stop')
        self.ssh.close()

    def restart(self):
        self.ssh.connect(self.host, username=self.user, password=self.password)
        self.ssh.exec_command('sudo service haproxy restart')
        self.ssh.close()


class RemoteInterface(object):
    def __init__(self, device_ref, frontend):
        self.interface = device_ref['interface']
        self.IP = frontend.bind_address
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.host = device_ref['ip']
        self.user = device_ref['login']
        self.password = device_ref['password']

    def change_ip(self, IP, netmask):
        self.ssh.connect(self.host, username=self.user, password=self.password)
        self.ssh.exec_command("sudo ifconfig  %s %s %s" %
                                (self.interface,  IP,  netmask))
        self.ssh.close()

    def add_ip(self):
        self.ssh.connect(self.host, username=self.user, password=self.password)
        logger.debug('[HAPROXY] try add IP-%s to inteface %s' %
                                (self.IP,  self.interface))
        stdin, stdout, stderr = self.ssh.exec_command('ip addr show dev %s' %
                                self.interface)
        ssh_out = stdout.read()
        if ssh_out.find(self.IP) < 0:
            self.ssh.exec_command('sudo ip addr add %s/32 dev %s' %
                                                (self.IP, self.interface))
            logger.debug('[HAPROXY] remote add ip %s to inteface %s' %
                                              (self.IP, self.interface))
        else:
            logger.debug('[HAPROXY] remote ip %s is already configured on the \
                                              %s' % (self.IP, self.interface))
        self.ssh.close()

    def del_ip(self):
        self.ssh.connect(self.host, username=self.user, password=self.password)
        stdin, stdout, stderr = self.ssh.exec_command('ip addr show dev %s' %
                               (self.interface))
        ssh_out = stdout.read()
        if  ssh_out.find(self.IP) >= 0:
            logger.debug('[HAPROXY] remote delete ip %s from inteface %s' %
                                    (self.IP, self.interface))
            self.ssh.exec_command('sudo ip addr del %s/32 dev %s' % (self.IP,
                                                   self.interface))
        else:
            logger.debug('[HAPROXY] remote ip %s is not configured on the %s' %
                                    (self.IP, self.interface))
        self.ssh.close()


class RemoteSocketOperation(object):
    '''
    Remote operations via haproxy socket
    '''
    def __init__(self, device_ref, backend, rserver,
                        interface, haproxy_socket):
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.host = device_ref['ip']
        self.user = device_ref['login']
        self.password = device_ref['password']
        self.interface = interface
        self.haproxy_socket = haproxy_socket
        self.backend_name = backend.name
        self.rserver_name = rserver['name']

    def suspend_server(self):
        self._operation_with_server_via_socket('disable')

    def activate_server(self):
        self._operation_with_server_via_socket('enable')

    def _operation_with_server_via_socket(self, operation):
        self.ssh.connect(self.host, username=self.user, password=self.password)
        stdin, stdout, stderr = self.ssh.exec_command(
                'echo %s server %s/%s | sudo socat stdio unix-connect:%s' %
                (operation,  self.backend_name,
                 self.rserver_name, self.haproxy_socket))
        ssh_out = stdout.read()
        if  ssh_out == "":
            out = 'ok'
        logger.debug('[HAPROXY] disable server %s/%s. Result is "%s"' %
                      (self.backend_name, self.rserver_name, out))
        self.ssh.close()

    def get_statistics(self):
        """
            Get statistics from rserver / server farm
            for all serverafarm use BACKEND as self.rserver_name
        """
        self.ssh.connect(self.host, username=self.user, password=self.password)
        stdin, stdout, stderr = self.ssh.exec_command(
           'echo show stat | sudo socat stdio unix-connect:%s | grep %s,%s ' %
            (self.haproxy_socket, self.backend_name, self.rserver_name))
        ssh_out = stdout.read()
        logger.debug('[HAPROXY] get statistics about reserver %s/%s.'
                    ' Result is \'%s\' ', self.backend_name, self.rserver_name,
                    out)
        self.ssh.close()
        return ssh_out
