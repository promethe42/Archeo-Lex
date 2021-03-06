# -*- coding: utf-8 -*-
# 
# Archéo Lex – Pure Histoire de la Loi française
# – crée un dépôt Git des lois françaises écrites en syntaxe Markdown
# – ce module assemble les textes et fait l’export final
# 
# This program is free software. It comes without any warranty, to
# the extent permitted by applicable law. You can redistribute it
# and/or modify it under the terms of the Do What The Fuck You Want
# To Public License, Version 2, as published by Sam Hocevar. See
# the LICENSE file for more details.

# Imports
from __future__ import unicode_literals
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
import os
import subprocess
import datetime
import time
import re
from pytz import timezone
from string import strip, join
from path import Path
from bs4 import BeautifulSoup
import legi
import legi.utils
from marcheolex import logger
from marcheolex import version_archeolex
from marcheolex import natures
from marcheolex.markdownlegi import creer_markdown
from marcheolex.markdownlegi import creer_markdown_texte
from marcheolex.utilitaires import normalisation_code
from marcheolex.utilitaires import chemin_texte
from marcheolex.utilitaires import nop
from marcheolex.utilitaires import MOIS
from marcheolex.utilitaires import MOIS2
from marcheolex.utilitaires import comp_infini
from marcheolex.utilitaires import comp_infini_strict


def creer_historique_legi(textes, format, dossier, cache, bdd):

    if len( textes ) == 1 and textes[0] == 'tout':
        db = legi.utils.connect_db(bdd)
        liste_textes = db.all("""
              SELECT cid
              FROM textes_versions
              ORDER BY cid
        """)
        liste_textes = [ x[0] for x in liste_textes ]
    elif len( textes ) == 1 and textes[0] == 'tout-obsolete':
        db = legi.utils.connect_db(bdd)
        last_update = db.one("""
            SELECT value
            FROM db_meta
            WHERE key = 'last_update'
        """)
        liste_textes = db.all("""
              SELECT cid
              FROM textes_versions
              WHERE mtime > {0}
              ORDER BY cid
        """.format(last_update))
        liste_textes = [ x[0] for x in liste_textes ]
        print( '\nListe de textes :\n' + join( liste_textes, '\n' ) + '\n' )
    elif len( textes ) == 1 and re.match( r'^aleatoire-([0-9]+)$', textes[0] ):
        db = legi.utils.connect_db(bdd)
        m = re.match( r'^aleatoire-([0-9]+)$', textes[0] )
        m = int( m.group(1) )
        liste_textes = db.all("""
              SELECT cid
              FROM textes_versions
              ORDER BY RANDOM()
              LIMIT {0}
        """.format(m))
        liste_textes = [ x[0] for x in liste_textes ]
        print( '\nListe de textes :\n' + join( liste_textes, '\n' ) + '\n' )
    elif len( textes ) == 1 and os.path.exists( textes[0] ):
        f_textes = open( textes[0], 'r' )
        liste_textes = strip(f_textes.read().decode('utf-8')).split('\n')
        f_textes.close()
    else:
        liste_textes = textes

    for texte in liste_textes:
        print( '> Texte {0}'.format( texte ) )
        creer_historique_texte(texte, format, dossier, cache, bdd)


def creer_historique_texte(texte, format, dossier, cache, bdd):

    # Constantes
    paris = timezone( 'Europe/Paris' )

    # Connexion à la base de données
    db = legi.utils.connect_db(bdd)

    # Créer le dossier si besoin
    sousdossier = '.'
    id = texte
    nom = texte

    # Flags: 1) s’il y a des versions en vigueur future, 2) si la première version est une vigueur future
    futur = False
    futur_debut = False

    # Obtenir la date de la base LEGI
    last_update = db.one("""
        SELECT value
        FROM db_meta
        WHERE key = 'last_update'
    """)
    last_update_jour = datetime.date(*(time.strptime(last_update, '%Y%m%d-%H%M%S')[0:3]))
    last_update = paris.localize( datetime.datetime(*(time.strptime(last_update, '%Y%m%d-%H%M%S')[0:6])) )
    logger.info('Dernière mise à jour de la base LEGI : {}'.format(last_update.isoformat()))

    Path(dossier).mkdir_p()
    entree_texte = db.one("""
        SELECT id, nature, titre, titrefull, etat, date_debut, date_fin, num, cid, mtime
        FROM textes_versions
        WHERE id = '{0}'
    """.format(id))
    if entree_texte == None:
        entree_texte = db.one("""
            SELECT id, nature, titre, titrefull, etat, date_debut, date_fin, num, cid, mtime
            FROM textes_versions
            WHERE cid = '{0}'
        """.format(id))
    if entree_texte == None:
        raise Exception('Pas de texte avec cet ID ou CID')
    cid = entree_texte[8]
    mtime = entree_texte[9]
    if entree_texte[1] in natures.keys():
        if not os.path.exists(os.path.join(dossier, natures[entree_texte[1]]+'s')):
            os.makedirs(os.path.join(dossier, natures[entree_texte[1]]+'s'))
        sousdossier = natures[entree_texte[1]]+'s'

    mise_a_jour = True
    if entree_texte[1] and (entree_texte[1] in natures.keys()) and entree_texte[7]:
        identifiant = natures[entree_texte[1]]+' '+entree_texte[7]
        identifiant = identifiant.replace(' ','_')
        nom_fichier = identifiant
        sousdossier = os.path.join(natures[entree_texte[1]]+'s', identifiant)
        if not os.path.exists(os.path.join(dossier, sousdossier)):
            mise_a_jour = False
        Path(os.path.join(dossier, sousdossier)).mkdir_p()
        chemin_base = chemin_texte(id, entree_texte[1] == 'CODE')
    elif entree_texte[1] and (entree_texte[1] in natures.keys()) and entree_texte[2]:
        identifiant = entree_texte[2][0].lower()+entree_texte[2][1:].replace(' ','_')
        nom_fichier = identifiant
        sousdossier = os.path.join(natures[entree_texte[1]]+'s', identifiant)
        if not os.path.exists(os.path.join(dossier, sousdossier)):
            mise_a_jour = False
        Path(os.path.join(dossier, sousdossier)).mkdir_p()
        chemin_base = chemin_texte(id, entree_texte[1] == 'CODE')
    else:
        raise Exception('Type bizarre ou inexistant')
        sousdossier = os.path.join(sousdossier, nom)
        nom_fichier = id
    dossier = os.path.join(dossier, sousdossier)
    sousdossier = '.'
    if not os.path.exists(dossier):
        os.makedirs(dossier)
    fichier = os.path.join(dossier, nom_fichier + '.md')

    # Créer le dépôt Git avec comme branche maîtresse 'texte' ou 'articles'
    branche = 'texte'
    if format['organisation'] == 'repertoires-simple':
        branche = 'articles'
    if not os.path.exists(os.path.join(dossier, '.git')):
        subprocess.call(['git', 'init'], cwd=dossier)
        subprocess.call(['git', 'symbolic-ref', 'HEAD', 'refs/heads/'+branche], cwd=dossier)
    else:
        subprocess.call(['git', 'checkout', '--', sousdossier], cwd=dossier)
    
    date_reprise_git = None
    reset_hash = ''
    if mise_a_jour:
        tags = subprocess.check_output(['git', 'tag', '-l'], cwd=dossier)
        tags = strip(tags).split('\n')
        date_maj_git = False
        if len(tags) == 0:
            raise Exception('Pas de tag de la dernière mise à jour')
        date_maj_git = paris.localize( datetime.datetime(*(time.strptime(tags[-1], '%Y%m%d-%H%M%S')[0:6])) )
        logger.info('Dernière mise à jour du dépôt : {}'.format(date_maj_git.isoformat()))
        if int(time.mktime(date_maj_git.timetuple())) >= mtime:
            logger.info('Pas de mise à jour disponible')
            return

        # Obtention de la première date qu’il faudra mettre à jour
        date_reprise_git = db.one("""
            SELECT date_debut
            FROM articles
            WHERE cid = '{0}' AND mtime > {1}
        """.format(cid,int(time.mktime(date_maj_git.timetuple()))))

        # Lecture des versions en vigueur dans le dépôt Git
        try:
            if subprocess.check_output(['git', 'rev-parse', '--verify', 'futur-'+branche], cwd=dossier):
                subprocess.call(['git', 'checkout', 'futur-'+branche], cwd=dossier)
        except subprocess.CalledProcessError:
            pass
        versions_git = strip(subprocess.check_output(['git', 'log', '--oneline'], cwd=dossier).decode('utf-8')).split('\n')
        for log_version in versions_git:
            for m, k in MOIS.items():
                log_version = log_version.replace( m, k )
            m = re.match(r'^([0-9a-f]+) .* ([0-9]+)(?:er)? ([0-9]+) ([0-9]+)$', log_version.encode('utf-8'))
            if not m:
                raise Exception('Version non reconnue dans le dépôt Git')
            date = '{0:04d}-{1:02d}-{2:02d}'.format(int(m.group(4)), int(m.group(3)), int(m.group(2)))
            reset_hash = m.group(1)
            if date < date_reprise_git:
                break
            reset_hash = ''

        if reset_hash:
            if date_reprise_git <= last_update_jour.strftime('%Y-%m-%d'):
                subprocess.call(['git', 'checkout', branche], cwd=dossier)
                try:
                    if subprocess.check_output(['git', 'rev-parse', '--verify', 'futur-'+branche], cwd=dossier):
                        subprocess.call(['git', 'branch', '-D', 'futur-'+branche], cwd=dossier)
                except subprocess.CalledProcessError:
                    pass
            subprocess.call(['git', 'reset', '--hard', reset_hash], cwd=dossier) 
        else:
            subprocess.call(['git', 'branch', '-m', 'texte', 'junk'], cwd=dossier)
            subprocess.call(['git', 'checkout', '--orphan', branche], cwd=dossier)
            subprocess.call(['git', 'branch', '-D', 'junk'], cwd=dossier)

    # Vérifier que les articles ont été transformés en Markdown ou les créer le cas échéant
    creer_markdown_texte((None, cid, None, None), db, cache)
    
    # Sélection des versions du texte
    versions_texte_db = db.all("""
          SELECT debut, fin
          FROM sommaires
          WHERE cid = '{0}'
          ORDER BY debut
    """.format(cid))
    dates_texte = []
    dates_fin_texte = []
    versions_texte = []
    for vers in versions_texte_db:
        vt = vers[0]
        if isinstance(vt, basestring):
            vt = datetime.date(*(time.strptime(vt, '%Y-%m-%d')[0:3]))
        if date_reprise_git and vt.strftime('%Y-%m-%d') < date_reprise_git:
            continue
        dates_texte.append( vt )
        vt = vers[1]
        if isinstance(vt, basestring):
            vt = datetime.date(*(time.strptime(vt, '%Y-%m-%d')[0:3]))
        dates_fin_texte.append( vt )
    versions_texte = sorted(set(dates_texte).union(set(dates_fin_texte)))
    
    sql_texte = "cid = '{0}'".format(cid)
    versions_texte = sorted(list(set(versions_texte)))

    # Pour chaque version
    # - rechercher les sections et articles associés
    # - créer le fichier texte au format demandé
    # - commiter le fichier
    for (i_version, version_texte) in enumerate(versions_texte):
        
        # Passer les versions 'nulles'
        #if version_texte.base is None:
        #    continue
        if i_version >= len(versions_texte)-1:
            break

        debut = versions_texte[i_version]
        fin = versions_texte[i_version+1]
        debut_datetime = paris.localize( datetime.datetime( debut.year, debut.month, debut.day ) )

        if not futur and debut > last_update_jour:
            if i_version == 0:
                subprocess.call(['git', 'symbolic-ref', 'HEAD', 'refs/heads/futur-'+branche], cwd=dossier)
                if not reset_hash:
                    futur_debut = True
            else:
                subprocess.call(['git', 'checkout', '-b', 'futur-'+branche], cwd=dossier)
            futur = True

        sql = sql_texte + " AND debut <= '{0}' AND ( fin >= '{1}' OR fin == '2999-01-01' OR etat == 'VIGUEUR' )".format(debut,fin)

        # Créer l’en-tête
        date_fr = '{} {} {}'.format(debut.day, MOIS2[int(debut.month)], debut.year)
        if debut.day == 1:
            date_fr = '1er {} {}'.format(MOIS2[int(debut.month)], debut.year)
        contenu = nom + '\n'   \
                  + '\n'   \
                  + '- Date de consolidation : ' + date_fr + '\n'            \
                  + '- [Lien permanent Légifrance](https://www.legifrance.gouv.fr/affichCode.do?cidTexte=' + cid + '&dateTexte=' + debut.isoformat().replace('-','') + ')\n' \
                  + '\n' \
                  + '\n'

        # Enregistrement du fichier
        if format['organisation'] != 'fichier-unique':
            f_texte = open('README.md', 'w')
            f_texte.write(contenu.encode('utf-8'))
            f_texte.close()

            # Retrait des fichiers des anciennes versions
            subprocess.call('rm *.md', cwd=dossier, shell=True)

        # Créer les sections (donc tout le texte)
        contenu = creer_sections(contenu, 1, None, (debut,fin), sql, [], format, dossier, db, cache)
        
        # Enregistrement du fichier
        if format['organisation'] == 'fichier-unique':
            f_texte = open(fichier, 'w')
            f_texte.write(contenu.encode('utf-8'))
            f_texte.close()
        
        # Exécuter Git
        subprocess.call(['git', 'add', '.'], cwd=dossier)
        #subprocess.call(['git', 'commit', '--author="Législateur <>"', '--date="' + str(debut_datetime) + '"', '-m', 'Version consolidée au {}\n\nVersions :\n- base LEGI : {}\n- programme Archéo Lex : {}'.format(date_fr, date_base_legi, version_archeolex), '-q', '--no-status'], cwd=dossier)
        subprocess.call(['git', 'commit', '--author="Législateur <>"', '--date="' + str(debut_datetime) + '"', '-m', 'Version consolidée au {}'.format(date_fr), '-q', '--no-status'], cwd=dossier, env={ 'GIT_COMMITTER_DATE': last_update.isoformat(), 'GIT_COMMITTER_NAME': 'Législateur'.encode('utf-8'), 'GIT_COMMITTER_EMAIL': '' })
        
        if fin == None or str(fin) == '2999-01-01':
            logger.info('Version {} enregistrée (du {} à maintenant)'.format(i_version+1, debut))
        else:
            logger.info('Version {} enregistrée (du {} au {})'.format(i_version+1, debut, fin))
    
    if futur and not futur_debut:
        subprocess.call(['git', 'checkout', branche], cwd=dossier)
    
    # Optimisation du dossier git
    subprocess.call(['git', 'gc', '--aggressive'], cwd=dossier)
    subprocess.call('rm -rf .git/hooks .git/refs/heads .git/refs/tags .git/logs .git/COMMIT_EDITMSG .git/branches', cwd=dossier, shell=True)
    subprocess.call('chmod -x .git/config', cwd=dossier, shell=True)

    # Ajout du tag de date éditoriale
    subprocess.call(['git', 'tag', last_update.strftime('%Y%m%d-%H%M%S')], cwd=dossier)

    # Suppression du cache
    subprocess.call('rm -rf markdown/{0}'.format(cid), cwd=cache, shell=True)


def creer_sections(texte, niveau, parent, version_texte, sql, arborescence, format, dossier, db, cache):
 
    marque_niveau = ''
    for i in range(niveau):
        marque_niveau = marque_niveau + '#'

    sql_section_parente = "parent = '{0}'".format(parent)
    if parent == None:
        sql_section_parente = "parent IS NULL OR parent = ''"

    sections = db.all("""
        SELECT *
        FROM sommaires
        WHERE ({0})
          AND ({1})
        ORDER BY position
    """.format(sql_section_parente, sql))

    # Itérer sur les sections de cette section
    for section in sections:

        rcid, rparent, relement, rdebut, rfin, retat, rnum, rposition, r_source = section

        if comp_infini_strict(version_texte[0], rdebut) or (comp_infini_strict(rfin, version_texte[1]) and retat != 'VIGUEUR'):
            raise Exception(u'section non valide (version texte de {} a {}, version section de {} à {})'.format(version_texte[0], version_texte[1], rdebut, rfin))
            return texte

        # L’élément est un titre de sommaire, rechercher son texte et l’ajouter à la liste
        if relement[4:8] == 'SCTA':
            tsection = db.one("""
                SELECT titre_ta, commentaire
                FROM sections
                WHERE id='{0}'
            """.format(relement))
            rarborescence = arborescence
            rarborescence.append( tsection[0].strip() )
            texte = texte                                  \
                    + marque_niveau + ' ' + tsection[0].strip() + '\n' \
                    + '\n'
            texte = creer_sections(texte, niveau+1, relement, version_texte, sql, rarborescence, format, dossier, db, cache)

        # L’élément est un article, l’ajouter à la liste
        elif relement[4:8] == 'ARTI':

            article = db.one("""
                SELECT id, section, num, date_debut, date_fin, bloc_textuel, cid
                FROM articles
                WHERE id = '{0}'
            """.format(relement))
            id, section, num, date_debut, date_fin, bloc_textuel, cid = article
            if comp_infini_strict(version_texte[0], date_debut) or (comp_infini_strict(date_fin, version_texte[1]) and retat != 'VIGUEUR'):
                continue
            chemin_markdown = os.path.join(cache, 'markdown', cid, id + '.md')
            f_article = open(chemin_markdown, 'r')
            texte_article = f_article.read().decode('utf-8')
            f_article.close()
 
            texte = texte                                                                    \
                    + marque_niveau + ' Article' + (' ' + num.strip() if num else '') + '\n' \
                    + '\n'                                                                   \
                    + texte_article + '\n'                                                   \
                    + '\n'                                                                   \
                    + '\n'

            # Format « 1 dossier = 1 article »
            fichier = os.path.join(dossier, 'Article_' + (num.replace(' ', '_') if num else relement) + '.md')
            if format['organisation'] == 'repertoires-simple':
                texte_article = texte_article + '\n'
                f_texte = open(fichier, 'w')
                f_texte.write(texte_article.encode('utf-8'))
                f_texte.close()

    return texte

# vim: set ts=4 sw=4 sts=4 et:
