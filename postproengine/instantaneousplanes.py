# Get the location where this script is being run
import sys, os
scriptpath = os.path.dirname(os.path.realpath(__file__))
basepath   = os.path.dirname(scriptpath)
# Add any possible locations of amr-wind-frontend here
amrwindfedirs = ['../',
                 basepath]
for x in amrwindfedirs: sys.path.insert(1, x)

from postproengine import registerplugin, mergedicts, registeraction
from postproengine import compute_axis1axis2_coords, interpolatetemplate
import postproamrwindsample_xarray as ppsamplexr
import postproamrwindsample as ppsample
import numpy as np
import pickle
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1 import make_axes_locatable
from postproengine import convert_vel_xyz_to_axis1axis2
import cv2
from postproengine import spod
import re
import plotfunctions

try:
    import imageio
    hasimageio = True
except:
    hasimageio = False

"""
Plugin for creating instantaneous planar images

See README.md for details on the structure of classes here
"""

@registerplugin
class postpro_instantaneousplanes():
    """
    Make plots of instantaneous planes
    """
    # Name of task (this is same as the name in the yaml
    name      = "instantaneousplanes"
    # Description of task
    blurb     = "Make instantaneous plots from netcdf sample planes"
    inputdefs = [
        # -- Required parameters ----
        {'key':'name',     'required':True,  'default':'',
         'help':'An arbitrary name',},
        {'key':'ncfile',   'required':True,  'default':'',
        'help':'NetCDF sampling file', },
        {'key':'iters',    'required':False,  'default':[],
        'help':'Which iterations to pull from netcdf file', },
        {'key':'times',    'required':False,  'default':None,
         'help':'Which times to pull from netcdf file', },        
        {'key':'trange',    'required':False,  'default':None,
         'help':'Pull a range of times from netcdf file', },        
        {'key':'xaxis',    'required':True,  'default':'x',
        'help':'Which axis to use on the abscissa', },
        {'key':'yaxis',    'required':True,  'default':'y',
        'help':'Which axis to use on the ordinate', },
        {'key':'iplane',   'required':True,  'default':0,
         'help':'Which plane to pull from netcdf file', },
        # --- optional parameters ---
        {'key':'group',   'required':False,  'default':None,
         'help':'Which group to pull from netcdf file', },
        {'key':'varnames',  'required':False,  'default':['velocityx', 'velocityy', 'velocityz'],
         'help':'Variables to extract from the netcdf file',},        
        {'key':'savepklfile', 'required':False,  'default':'',
         'help':'Name of pickle file to save results', },

    ]
    actionlist = {}                    # Dictionary for holding sub-actions
    example = """
```yaml
instantaneousplanes:
  name: Wake YZ plane
  ncfile: ./data_converter/PA_1p25_new2/YZslice_01.00D_456.00s_1556.00s_n1m.nc
  iters: [0,10,20]
  trange: [456,1056]
  times: [1100,1200,1300]
  xaxis: 'y'
  yaxis: 'z'
  varnames: ['velocityx','velocityy','velocityz']
  iplane: 0

  plot:
    plotfunc: "lambda db, i: db['velocityx'][i]"
    savefile: 'inst_figs_n1m/inst_test_{iter}.png'
    figsize: [8,5]
    dpi: 125
    xlabel: 'Y [m]'
    ylabel: 'Z [m]'
    clevels: 'np.linspace(2,7,121)'
    cbar: False
    cmap: 'viridis'

  animate:
    name: 'output.mp4'
    fps: 20
    imagefilename: './inst_figs_n1m/inst_test_{iter}.png'
    #times: 'np.arange(456,1556.5,0.5)'

  plot_radial:
    plotfunc: "lambda db, i: db['velocityx'][i]"
    savefile: 'radial_test_{time}.png'
    figsize: [8,5]
    dpi: 125
    clevels: 'np.linspace(2,7,121)'
    cmap: 'viridis'
    LR: 89.0
    NR: 256
    NTheta: 256
    vmin: 2
    vmax: 7
    xc: 375
    yc: 90
    cbar: True
```
"""


    # --- Stuff required for main task ---
    def __init__(self, inputs, verbose=False):
        self.yamldictlist = []
        inputlist = inputs if isinstance(inputs, list) else [inputs]
        for indict in inputlist:
            self.yamldictlist.append(mergedicts(indict, self.inputdefs))
        if verbose: print('Initialized '+self.name)
        return
    
    def execute(self, verbose=False):
        if verbose: print('Running '+self.name)
        # Loop through and create plots
        for planeiter , plane in enumerate(self.yamldictlist):
            iters    = plane['iters']
            ncfile   = plane['ncfile']
            self.xaxis    = plane['xaxis']
            self.yaxis    = plane['yaxis']
            savepklfile   = plane['savepklfile']

            # Load optional quantities
            self.times    = plane['times']
            self.trange   = plane['trange']
            group    = plane['group']
            varnames = plane['varnames']
            self.iplane = plane['iplane']

            # Load the plane
            self.db  = ppsamplexr.getPlaneXR(ncfile, iters, varnames, groupname=group, verbose=verbose, gettimes=True, includeattr=True,timerange=self.trange,times=self.times)

            # Convert to native axis1/axis2 coordinates if necessary
            if ('a1' in [self.xaxis, self.yaxis]) or \
               ('a2' in [self.xaxis, self.yaxis]) or \
               ('a3' in [self.xaxis, self.yaxis]):
                compute_axis1axis2_coords(self.db)

            if not self.trange == 'None':
                iters = self.db['timesteps']

            self.iters = iters

            if len(savepklfile)>0:
                # Write out the picklefile
                dbfile = open(savepklfile, 'wb')
                pickle.dump(self.db, dbfile, protocol=2)
                dbfile.close()

            # Do any sub-actions required for this task
            for a in self.actionlist:
                action = self.actionlist[a]
                # Check to make sure required actions are there
                if action.required and (action.actionname not in self.yamldictlist[planeiter].keys()):
                    # This is a problem, stop things
                    raise ValueError('Required action %s not present'%action.actionname)
                if action.actionname in self.yamldictlist[planeiter].keys():
                    actionitem = action(self, self.yamldictlist[planeiter][action.actionname])
                    actionitem.execute()
        return

    @registeraction(actionlist)
    class plot():
        actionname = 'plot'
        blurb      = 'Plot instantaneous fields for all iterations'
        required   = False
        actiondefs = [
            {'key':'title',     'required':False,  'default':'',
            'help':'Title of the plot',},
            {'key':'plotfunc',  'required':False,
            'default':"lambda db,i: np.sqrt(db['velocityx'][i]**2 + db['velocityy'][i]**2)",
            'help':'Function to plot (lambda expression)',},
            {'key':'clevels',   'required':False,  'default':'np.linspace(0, 12, 121)',
            'help':'Color levels (eval expression)',},
            {'key':'cmap',   'required':False,  'default':'coolwarm',
            'help':'Color map name',},
            {'key':'cbar',   'required':False,  'default':True,
            'help':'Boolean to include colorbar',},
            {'key':'cbar_label',   'required':False,  'default':None,
            'help':'Label for colorbar',},
            {'key':'cbar_nticks', 'required':False,  'default':None,
            'help':'Number of ticks to include on colorbar',},
            {'key':'xlabel',    'required':False,  'default':'X [m]',
            'help':'Label on the X-axis', },
            {'key':'ylabel',    'required':False,  'default':'Y [m]',
            'help':'Label on the Y-axis', },
            {'key':'xlim',    'required':False,  'default':None,
            'help':'Axis bounds on the X-axis', },
            {'key':'ylim',    'required':False,  'default':None,
            'help':'Axis bounds on the Y-axis', },
            {'key':'dpi',       'required':False,  'default':125,
            'help':'Figure resolution', },
            {'key':'figsize',   'required':False,  'default':[12,3],
            'help':'Figure size (inches)', },
            {'key':'fontsize',   'required':False,  'default':14,
            'help':'Fontsize for labels and axis', },
            {'key':'savefile',  'required':False,  'default':'',
            'help':'Filename to save the picture', },
            {'key':'postplotfunc', 'required':False,  'default':'',
            'help':'Function to call after plot is created. Function should have arguments func(fig, ax)',},
            {'key':'xscalefunc',  'required':False,  'default':'lambda x: x',
             'help':'Function to scale the x-axis (lambda expression)',},
            {'key':'yscalefunc',  'required':False,  'default':'lambda y: y',
             'help':'Function to scale the y-axis (lambda expression)',},
            {'key':'figname',    'required':False,  'default':None,
             'help':'Name/number of figure to create plot in'},
            {'key':'axesnumfunc',    'required':False,  'default':None,
             'help':'Function to determine which subplot axes to create plot in (lambda expression with iplane as arg)'},
            {'key':'axesnumfunc',    'required':False,  'default':None,
             'help':'Function to determine which subplot axes to create plot in (lambda expression with iplane as arg)'},
            {'key':'axisscale',    'required':False,  'default':'scaled',
             'help':'Aspect ratio of figure axes (options:equal,scaled,tight,auto,image,square)'},
            {'key':'plotturbines',   'required':False,  'default':None,
             'help':'List of dictionaries which contain turbines to plot', },

        ]
        def __init__(self, parent, inputs):
            self.actiondict = mergedicts(inputs, self.actiondefs)
            self.parent = parent
            print('Initialized '+self.actionname+' inside '+parent.name)
            return

        def execute(self):
            print('Executing ' + self.actionname)
            plotfunc = eval(self.actiondict['plotfunc'])
            title    = self.actiondict['title']
            clevels  = eval(self.actiondict['clevels'])
            cmap     = self.actiondict['cmap']
            cbar_inc = self.actiondict['cbar']
            cbar_nticks = self.actiondict['cbar_nticks']
            cbar_label = self.actiondict['cbar_label']
            xlabel   = self.actiondict['xlabel']
            ylabel   = self.actiondict['ylabel']
            xlim     = self.actiondict['xlim']
            ylim     = self.actiondict['ylim']
            savefile = self.actiondict['savefile']
            dpi      = self.actiondict['dpi']
            figsize  = self.actiondict['figsize']
            fontsize = self.actiondict['fontsize']
            postplotfunc = self.actiondict['postplotfunc']
            xscalef  = eval(self.actiondict['xscalefunc'])
            yscalef  = eval(self.actiondict['yscalefunc'])
            figname  = self.actiondict['figname']
            axesnumf = None if self.actiondict['axesnumfunc'] is None else eval(self.actiondict['axesnumfunc'])
            axisscale= self.actiondict['axisscale']
            plotturbs= self.actiondict['plotturbines']

            # Loop through each time instance and plot
            iplane = self.parent.iplane
            for iplot, i in enumerate(self.parent.iters):
                time  = self.parent.db['times'][iplot]
                if (figname is not None) and (axesnumf is not None):
                    fig     = plt.figure(figname)
                    allaxes = fig.get_axes()
                    iax     = axesnumf(iplane)
                    ax      = allaxes[iax]
                else:
                    fig, ax = plt.subplots(1,1,figsize=(figsize[0],figsize[1]), dpi=dpi)
                plotq = plotfunc(self.parent.db, i)
                c = ax.contourf(xscalef(self.parent.db[self.parent.xaxis][iplane,:,:]),
                                yscalef(self.parent.db[self.parent.yaxis][iplane,:,:]),
                                plotq[iplane, :, :], levels=clevels, cmap=cmap, extend='both')
                if cbar_inc:
                    divider = make_axes_locatable(ax)
                    cax = divider.append_axes("right", size="3%", pad=0.05)
                    cbar=fig.colorbar(c, ax=ax, cax=cax)
                    cbar.ax.tick_params(labelsize=fontsize)
                    if cbar_label is not None:
                        cbar.set_label(cbar_label,fontsize=fontsize)

                    if cbar_nticks is not None:
                        levels = c.levels
                        # Define the number of intervals
                        min_tick = levels[0]
                        max_tick = levels[-1]
                        new_ticks = np.linspace(min_tick, max_tick, cbar_nticks)
                        cbar.set_ticks(new_ticks)

                if (xlabel is not None): ax.set_xlabel(xlabel,fontsize=fontsize)
                if (ylabel is not None): ax.set_ylabel(ylabel,fontsize=fontsize)
                ax.tick_params(axis='both', which='major', labelsize=fontsize) 
                # SET TITLE
                parts = re.split(r'(\$.*?\$)', title)
                evaluated_parts = []
                for part in parts:
                    if part.startswith('$') and part.endswith('$'):
                        # This part is inside LaTeX math mode, leave it as is
                        evaluated_parts.append(part)
                    else:
                        # This part is outside LaTeX math mode, evaluate it
                        evaluated_parts.append(eval(f"rf'{part}'"))
                evaltitle = ''.join(evaluated_parts)
                ax.set_title(evaltitle,fontsize=fontsize)
                if axisscale is not None:
                    ax.axis(axisscale)

                if xlim is not None:
                    ax.set_xlim(xlim[0],xlim[1])

                if ylim is not None:
                    ax.set_ylim(ylim[0],ylim[1])

                # Plot turbines
                if plotturbs:
                    axismapping = {'x':0, 'a1':0, 'y':1, 'a2':1, 'z':2, 'a3':2}
                    defaultlstyle =  {'lw':1, 'color':'k', 'alpha':0.75}
                    for turb in plotturbs:
                        basexyz   = turb['basexyz']
                        hubheight = turb['hubheight']
                        turbD     = turb['rotordiameter']
                        nacelledir= turb['nacelledir']
                        ix        = turb['ix'] if 'ix' in turb else axismapping[self.parent.xaxis]
                        iy        = turb['iy'] if 'iy' in turb else axismapping[self.parent.yaxis]
                        lstyle    = turb['linestyle'] if 'linestyle' in turb else defaultlstyle
                        plotfunctions.plotTurbine(ax, basexyz, hubheight, turbD, nacelledir, ix, iy,
                                                  **lstyle)

                # Run any post plot functions
                if len(postplotfunc)>0:
                    modname = postplotfunc.split('.')[0]
                    funcname = postplotfunc.split('.')[1]
                    func = getattr(sys.modules[modname], funcname)
                    func(fig, ax)

                if len(savefile)>0:
                    savefname = savefile.format(time=time, iplane=iplane, iter=i)
                    directory, file_name = os.path.split(savefname)
                    directory += '/'
                    os.makedirs(directory, exist_ok=True)
                    plt.savefig(savefname)
        

    # --- Inner classes for action list ---
    @registeraction(actionlist)
    class interpolate(interpolatetemplate):
        actionname = 'interpolate'
        def __init__(self, parent, inputs):
            super().__init__(parent, inputs)
            self.interpdb = self.parent.db
            self.iters    = self.parent.iters
            return


    @registeraction(actionlist)
    class animate():
        actionname = 'animate'
        blurb      = 'Generate animation from static images of planes'
        required   = False
        actiondefs = [
            {'key':'name', 'required':True,  'help':'Name of video', 'default':'output.mp4'},
            {'key':'fps', 'required':False,  'help':'Frame per second', 'default':1},
            {'key':'imagefilename', 'required':True,  'help':'savefile name of images', 'default':''},
            {'key':'times', 'required':False,  'help':'Override parent times for animation', 'default':None},
        ]
        def __init__(self, parent, inputs):
            self.actiondict = mergedicts(inputs, self.actiondefs)
            self.parent = parent
            print('Initialized '+self.actionname+' inside '+parent.name)
            return

        def execute(self):
            print('Executing ' + self.actionname)
            video_name = self.actiondict['name']
            directory, file_name = os.path.split(video_name)
            directory += '/'
            os.makedirs(directory, exist_ok=True)
            fps = self.actiondict['fps']
            imagefilename = self.actiondict['imagefilename']
            images = []
            iplane = self.parent.iplane
            #sort images by time
            iters = self.parent.iters
            for iplot, i in enumerate(iters):
                time  = self.parent.db['times'][iplot]
                images.append(imagefilename.format(time=time, iplane=iplane,iter=i))
            frame = cv2.imread(os.path.join(images[0]))
            height, width, layers = frame.shape
            video = cv2.VideoWriter(video_name, cv2.VideoWriter_fourcc(*'mp4v'), fps, (width, height))
            for image in images:
                video.write(cv2.imread(os.path.join(image)))
            cv2.destroyAllWindows()
            video.release()
            return

    @registeraction(actionlist)
    class makegif():
        actionname = 'makegif'
        blurb      = 'Generate an animated gif from static images of planes'
        required   = False
        actiondefs = [
            {'key':'name', 'required':True,  'help':'Name of video', 'default':'output.mp4'},
            {'key':'fps', 'required':False,  'help':'Frame per second', 'default':1},
            {'key':'imagefilename', 'required':True,  'help':'savefile name of images', 'default':''},
            {'key':'times', 'required':False,  'help':'Override parent times for animation', 'default':None},
        ]
        def __init__(self, parent, inputs):
            self.actiondict = mergedicts(inputs, self.actiondefs)
            self.parent = parent
            print('Initialized '+self.actionname+' inside '+parent.name)
            return

        def execute(self):
            if (not hasimageio):
                print('Cannot execute '+self.actionname)
                print('import imageio failed')
                return
            print('Executing ' + self.actionname)
            video_name = self.actiondict['name']
            directory, file_name = os.path.split(video_name)
            directory += '/'
            os.makedirs(directory, exist_ok=True)
            fps = self.actiondict['fps']
            imagefilename = self.actiondict['imagefilename']
            try:
                times = eval(self.actiondict['times'])
                override_times = True
            except:
                times = None
                override_times = False

            images = []
            iplane = self.parent.iplane
            #sort images by time
            if override_times:
                iters = range(len(times))
            else:
                iters = self.parent.iters
            for iplot, i in enumerate(iters):
                if override_times:
                    time = times[iplot]
                else:
                    time  = self.parent.db['times'][iplot]
                images.append(imagefilename.format(time=time, iplane=iplane))

            # Create an animated GIF from the movie frames
            imagedat=[]
            for f in images:
                img = cv2.imread(f)
                if img is not None:
                    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    imagedat.append(img_rgb)
            imageio.mimsave(video_name, imagedat, fps=fps)
            return

    @registeraction(actionlist)
    class plot_radial():
        actionname = 'plot_radial'
        blurb      = 'Plot instantaneous field in polar coordinate'
        required   = False
        actiondefs = [
            {'key':'title',     'required':False,  'default':'',
            'help':'Title of the plot',},
            {'key':'plotfunc',  'required':False,
            'default':"lambda db,i: db['velocityx'][i]",
            'help':'Function to plot (lambda expression)',},
            {'key':'cmap',   'required':False,  'default':'coolwarm',
            'help':'Color map name',},
            {'key':'cbar',   'required':False,  'default':True,
            'help':'Boolean to include colorbar',},
            {'key':'dpi',       'required':False,  'default':125,
            'help':'Figure resolution', },
            {'key':'figsize',   'required':False,  'default':[8,5],
            'help':'Figure size (inches)', },
            {'key':'savefile',  'required':False,  'default':'',
            'help':'Filename to save the picture', },
            {'key':'vmin','required':False,  'default':None,
            'help':'Minimum color range', },
            {'key':'vmax','required':False,  'default':None,
            'help':'Maximum color range', },
            {'key':'LR','required':True,  'default':None,
            'help':'Extent of radial grid', },
            {'key':'NR','required':True,  'default':256,
            'help':'Number of points in radial direction', },
            {'key':'NTheta','required':True,  'default':256,
            'help':'Number of points in azimuthal direction', },
        ]
        def __init__(self, parent, inputs):
            self.actiondict = mergedicts(inputs, self.actiondefs)
            self.parent = parent
            print('Initialized '+self.actionname+' inside '+parent.name)
            return

        def execute(self):
            print('Executing ' + self.actionname)
            plotfunc = eval(self.actiondict['plotfunc'])
            title    = self.actiondict['title']
            cmap     = self.actiondict['cmap']
            cbar_inc = self.actiondict['cbar']
            savefile = self.actiondict['savefile']
            dpi      = self.actiondict['dpi']
            figsize  = self.actiondict['figsize']
            NR       = self.actiondict['NR']
            NTheta   = self.actiondict['NTheta']
            LR       = self.actiondict['LR']
            vmin     = self.actiondict['vmin']
            vmax     = self.actiondict['vmax']
            xcenter  = self.actiondict['xc']
            ycenter  = self.actiondict['yc']

            LTheta = 2 * np.pi
            r = np.linspace(0,LR,NR)
            theta = np.linspace(0,LTheta,NTheta+1)[0:-1] #periodic grid in theta
            RR, TT = np.meshgrid(r,theta,indexing='ij')

            # Loop through each time instance and plot
            iplane = self.parent.iplane
            for iplot, i in enumerate(self.parent.iters):
                y = self.parent.db['y'][iplane,0,:]
                z = self.parent.db['z'][iplane,:,0]
                time  = self.parent.db['times'][iplot]
                fig, ax = plt.subplots(figsize=(figsize[0],figsize[1]),subplot_kw={'projection':'polar'},dpi=dpi)
                LR = r[-1]
                plotq = plotfunc(self.parent.db,i)
                Ur = spod.interpolate_cart_to_radial(plotq[iplane,:,:],y,z,RR,TT,xcenter,ycenter)
                if vmin == None or vmax == None:
                    im = ax.pcolormesh(theta,r,Ur,cmap=cmap)
                else:
                    im = ax.pcolormesh(theta,r,Ur,cmap=cmap,vmin=vmin,vmax=vmax)

                if cbar_inc:
                    plt.colorbar(im)
                ax.set_rmax(LR)
                ax.set_title(title)
                #ax.set_yticks([0,LR/1.4, LR])  # less radial ticks
                #ax.set_rlabel_position(-22.5)  # get radial labels away from plotted line
                #ax.set_yticklabels(["$0$","$R$","1.4$R$"])
                ax.grid(True)
                lines, labels = plt.thetagrids([0,45,90,135,180,225,270,315], ("$90^\circ$","$45^\circ$","$0^\circ$","$315^\circ$","$270^\circ$","$225^\circ$","$180^\circ$","$135^\circ$"))

                if len(savefile)>0:
                    savefname = savefile.format(time=time, iplane=iplane)
                    print('Saving '+savefname)
                    directory, file_name = os.path.split(savefname)
                    directory += '/'
                    os.makedirs(directory, exist_ok=True)
                    plt.savefig(savefname)

