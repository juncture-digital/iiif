copyright_statements = {
  'ALL RIGHTS RESERVED',
}

class CreativeCommonsLicense(object):

  default_version = '4.0'
  default_icon_width = 88
  default_icon_height = 31
  pd_license_url = 'http://creativecommons.org/publicdomain/zero/1.0/'
  license_url_template = 'http://creativecommons.org/licenses/{license_code}/{version}/'

  pd_icon_template = 'https://mirrors.creativecommons.org/presskit/buttons/{width}x{height}/png/cc-zero.png'
  icon_template = 'https://licensebuttons.net/l/{license_code}/{version}/{width}x{height}.png'

  licenses = {
    'CC0': 'Public Domain Dedication',
    'PD': 'Public Domain',
    'PUBLIC DOMAIN': 'Public Domain',
    'PDM': 'Public Domain Mark',
    'CC BY': 'Attribution',
    'CC BY-SA': 'Attribution-ShareAlike',
    'CC BY-ND': 'Attribution-NoDerivs',
    'CC BY-NC': 'Attribution-NonCommercial',
    'CC BY-NC-SA': 'Attribution-NonCommercial',
    'CC BY-NC-ND': 'Attribution-NonCommercial-NoDerivs'
  }

  def __init__(self, **kwargs):
    self._license = self._version = self.icon_width = self.icon_height = None
    self._license = kwargs.get('license')
    self._version == kwargs.get('version')
    self.icon_width == kwargs.get('icon_width')
    self.icon_height == kwargs.get('icon_height')

  def get_license(self):
    return self._license
  
  def set_license(self, license):
    self._license = license
  
  license = property(get_license, set_license)

  @property
  def is_pd(self):
    return self.license in ('CC0', 'PUBLIC DOMAIN',)

  def get_version(self):
    return self._version if self._version else '1.0' if self.is_pd else self.default_version
  
  def set_version(self, version):
    self._version = version
  
  version = property(get_version, set_version)

  @property
  def label(self):
    return self.licenses.get(self.license)

  @property
  def url(self):
    return self.pd_license_url if self.is_pd else self.license_url_template.format(license_code=self.license.split()[-1].lower(), version=self.version)

  @property
  def icon(self):
    if self.is_pd:
      return self.pd_icon_template.format(
      width=self.icon_width if self.icon_width else self.default_icon_width, 
      height=self.icon_height if self.icon_height else self.default_icon_height
    )
    return self.icon_template.format(
      license_code=self.license,
      version=self.version, 
      width=self.icon_width if self.icon_width else self.default_icon_width, 
      height=self.icon_height if self.icon_height else self.default_icon_height
    )

  def __str__(self):
    return f'{self._license} {self.version}'

class RightsStatement(object):

  default_version = '1.0'
  license_url_template = 'http://rightsstatements.org/vocab/{license_code}/{version}/'
  icon_template = 'https://rightsstatements.org/files/buttons/{license_code}.white.svg'
  icon_background_color = '318ac7'
  
  statements = {

    # Rights statements for in copyright objects
    'InC': 'IN COPYRIGHT',
    'InC-OW-EU': 'IN COPYRIGHT - EU ORPHAN WORK',
    'InC-EDU': 'IN COPYRIGHT - EDUCATIONAL USE PERMITTED',
    'InC-NC': 'IN COPYRIGHT - NON-COMMERCIAL USE PERMITTED',
    'InC-RUU': 'IN COPYRIGHT - RIGHTS-HOLDER(S) UNLOCATABLE OR UNIDENTIFIABLE',

    # Rights statements for objects that are not in copyright
    'NoC-CR': 'NO COPYRIGHT - CONTRACTUAL RESTRICTIONS',
    'NoC-NC': 'NO COPYRIGHT - NON-COMMERCIAL USE ONLY',
    'NoC-OKLR': 'NO COPYRIGHT - OTHER KNOWN LEGAL RESTRICTIONS',
    'NoC-US': 'NO COPYRIGHT - UNITED STATES',

    # Other rights statements
    'CNE': 'COPYRIGHT NOT EVALUATED',
    'UND': 'COPYRIGHT UNDETERMINED',
    'NKC': 'NO KNOWN COPYRIGHT',
  }

  def __init__(self, **kwargs):
    self._license = self._version = None
    self._license = kwargs.get('license')
    self._version == kwargs.get('version')

  def get_license(self):
    return self._license
  
  def set_license(self, license):
    self._license = license
  
  license = property(get_license, set_license)

  def get_version(self):
    return self._version if self._version else self.default_version
  
  def set_version(self, version):
    self._version = version
  
  version = property(get_version, set_version)

  @property
  def label(self):
    return self.statements.get(self.license)

  @property
  def url(self):
    return self.license_url_template.format(license_code=self.license, version=self.version)

  @property
  def icon(self):
    return self.icon_template.format(license_code=self.license)

  def __str__(self):
    return f'{self.label} {self.version}'